"""Pipeline orchestrator for managing persistent campaign step execution with retry and resumption."""

import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.conversation import copy
from app.conversation.state_machine import ConversationState
from app.llm.client import LLMClient, get_llm_client
from app.llm.schemas import ClipAnalysis, InsufficientFootage, Plan
from app.messaging.base import MessagingProvider
from app.models.base import utcnow
from app.models.entities import Business, Campaign, CampaignStep, Conversation, MediaAsset, Video
from app.pipeline.analyse import analyse_clips_parallel
from app.pipeline.download import normalize_media_clip
from app.pipeline.plan import BusinessContext, plan_ad_campaign
from app.pipeline.quality import QualityReport, run_pipeline_with_quality_autofix
from app.pipeline.render import render_video

logger = logging.getLogger(__name__)


class StepExecutionError(Exception):
    """Exception raised when a campaign step fails after maximum retry attempts."""

    pass


def build_business_context(business: Business) -> BusinessContext:
    """Construct BusinessContext from business ORM entity."""
    menu_items = [{"name": m.name, "price_inr": m.price_inr} for m in business.menu_items if m.is_active]
    return BusinessContext(
        name=business.name,
        category=business.category or "Food stall",
        language=business.language or "hinglish",
        landmark=business.landmark,
        brand_hex=business.brand_hex or "#FF5722",
        menu_items=menu_items,
    )


def execute_step(
    db: Session,
    campaign: Campaign,
    step_name: str,
    target_state: str,
    action: Callable[[], dict[str, Any]],
    max_retries: int = 3,
    backoff_base_s: float = 0.1,
) -> dict[str, Any]:
    """Execute a single pipeline step with idempotency, persistence, and exponential backoff.

    If the step has already succeeded (status == 'done'), cached output is returned without re-running.
    """
    step = (
        db.query(CampaignStep)
        .filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == step_name)
        .first()
    )
    if not step:
        step = CampaignStep(
            campaign_id=campaign.id,
            name=step_name,
            status="pending",
            attempts=0,
        )
        db.add(step)
        db.commit()

    if step.status == "done" and step.output_json is not None:
        logger.info(f"Campaign {campaign.id} step '{step_name}' already completed; skipping.")
        return step.output_json

    # Allow re-attempt if resuming a previously failed step
    if step.attempts >= max_retries:
        step.attempts = 0

    campaign.state = target_state
    db.commit()

    while step.attempts < max_retries:
        step.status = "running"
        step.attempts += 1
        step.started_at = utcnow()
        db.commit()

        try:
            output = action()
            step.output_json = output
            step.status = "done"
            step.finished_at = utcnow()
            step.error = None
            db.commit()
            return output
        except Exception as e:
            step.error = str(e)
            db.commit()
            logger.warning(
                f"Campaign {campaign.id} step '{step_name}' attempt {step.attempts}/{max_retries} failed: {e}"
            )
            if step.attempts < max_retries:
                if backoff_base_s > 0:
                    time.sleep(backoff_base_s * (2 ** (step.attempts - 1)))
            else:
                step.status = "failed"
                step.finished_at = utcnow()
                db.commit()
                raise StepExecutionError(f"Step '{step_name}' failed after {max_retries} attempts: {e}") from e

    raise StepExecutionError(f"Step '{step_name}' has exhausted maximum attempts ({max_retries}).")


def process_campaign(
    db: Session,
    campaign_id: int,
    provider: MessagingProvider,
    llm_client: LLMClient | None = None,
    out_base_dir: str | None = None,
    max_retries: int = 3,
    backoff_base_s: float = 0.1,
) -> Video | None:
    """Execute end-to-end video ad creation pipeline for a campaign with persistence and resumption."""
    client = llm_client or get_llm_client()
    campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
    if not campaign:
        raise ValueError(f"Campaign {campaign_id} not found")

    business = campaign.business
    conversation = db.query(Conversation).filter(Conversation.business_id == business.id).first()

    base_dir = Path(out_base_dir or f"data/campaigns/{campaign.id}")
    clips_dir = base_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    out_video_path = base_dir / "preview_v1.mp4"

    from app.pipeline.usage import (
        increment_monthly_usage,
        is_business_busy,
        is_monthly_limit_reached,
    )

    # Concurrency and usage guard
    if is_monthly_limit_reached(db, business.id):
        logger.warning(f"Business {business.id} has reached monthly limit")
        campaign.state = "CANCELLED"
        if conversation:
            conversation.state = ConversationState.READY
        db.commit()
        provider.send_text(business.phone_e164, copy.LIMIT_REACHED)
        return None

    if is_business_busy(db, business.id, exclude_campaign_id=campaign.id):
        logger.warning(f"Business {business.id} has another job actively running")
        provider.send_text(business.phone_e164, copy.JOB_IN_PROGRESS)
        return None

    try:
        # Step 1: Download & Normalize
        def _action_download() -> dict[str, Any]:
            assets = db.query(MediaAsset).filter(MediaAsset.campaign_id == campaign.id).all()
            if not assets:
                raise ValueError(f"No media assets found for campaign {campaign.id}")
            clips: dict[str, str] = {}
            for idx, asset in enumerate(assets, start=1):
                norm = normalize_media_clip(asset.path, clips_dir)
                clips[str(idx)] = str(norm)
            return {"clips": clips}

        download_out = execute_step(
            db, campaign, "download", "DOWNLOADING", _action_download, max_retries, backoff_base_s
        )
        normalized_clips: dict[int, Path] = {int(k): Path(v) for k, v in download_out["clips"].items()}

        # If cached files missing from disk, re-run download
        if not all(p.exists() for p in normalized_clips.values()):
            step = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == "download").first()
            if step:
                step.status = "pending"
                db.commit()
            download_out = execute_step(
                db, campaign, "download", "DOWNLOADING", _action_download, max_retries, backoff_base_s
            )
            normalized_clips = {int(k): Path(v) for k, v in download_out["clips"].items()}

        # Step 2: Analyse
        def _action_analyse() -> dict[str, Any]:
            from app.pipeline.cost import record_step_cost

            t0 = time.perf_counter()
            clip_items = [(cid, path) for cid, path in normalized_clips.items()]
            analyses_list = analyse_clips_parallel(clip_items, llm_client=client)
            dur = time.perf_counter() - t0
            record_step_cost(
                db,
                campaign.id,
                "analyse",
                input_tokens=len(clip_items) * 600,
                output_tokens=len(clip_items) * 150,
                render_seconds=dur,
            )
            return {"analyses": [a.model_dump() for a in analyses_list]}

        analyse_out = execute_step(
            db, campaign, "analyse", "ANALYSING", _action_analyse, max_retries, backoff_base_s
        )
        analyses: list[ClipAnalysis] = [ClipAnalysis.model_validate(x) for x in analyse_out["analyses"]]

        # Step 3: Plan
        biz_context = build_business_context(business)

        def _action_plan() -> dict[str, Any]:
            from app.pipeline.cost import record_step_cost

            t0 = time.perf_counter()
            plan_res = plan_ad_campaign(
                business=biz_context,
                owner_message=campaign.request_text or "",
                clip_analyses=analyses,
                llm_client=client,
            )
            dur = time.perf_counter() - t0
            record_step_cost(
                db,
                campaign.id,
                "plan",
                input_tokens=1200,
                output_tokens=400,
                render_seconds=dur,
            )
            if isinstance(plan_res, InsufficientFootage):
                return {"insufficient_footage": True, "tip": plan_res.tip}
            return {"plan": plan_res.model_dump()}

        plan_out = execute_step(
            db, campaign, "plan", "PLANNING", _action_plan, max_retries, backoff_base_s
        )

        if plan_out.get("insufficient_footage"):
            logger.warning(f"Footage insufficient for campaign {campaign.id}: {plan_out.get('tip')}")
            campaign.state = "INSUFFICIENT_FOOTAGE"
            if conversation:
                conversation.state = ConversationState.READY
            db.commit()
            msg = copy.BAD_FOOTAGE.format(tip=plan_out.get("tip"))
            provider.send_text(business.phone_e164, msg)
            return None

        plan_result = Plan.model_validate(plan_out["plan"])

        # Step 4: Render
        def _action_render() -> dict[str, Any]:
            from app.pipeline.cost import record_step_cost

            t0 = time.perf_counter()
            render_video(plan_result, biz_context, normalized_clips, out_video_path)
            dur = time.perf_counter() - t0
            record_step_cost(db, campaign.id, "render", render_seconds=dur)
            return {"video_path": str(out_video_path)}

        render_out = execute_step(
            db, campaign, "render", "RENDERING", _action_render, max_retries, backoff_base_s
        )
        rendered_path = Path(render_out["video_path"])
        if not rendered_path.exists():
            step = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == "render").first()
            if step:
                step.status = "pending"
                db.commit()
            render_out = execute_step(
                db, campaign, "render", "RENDERING", _action_render, max_retries, backoff_base_s
            )
            rendered_path = Path(render_out["video_path"])

        # Step 5: Quality Check
        def _action_quality() -> dict[str, Any]:
            from app.pipeline.cost import record_step_cost

            t0 = time.perf_counter()
            final_rendered, quality_report = run_pipeline_with_quality_autofix(
                plan=plan_result,
                business=biz_context,
                clip_paths=normalized_clips,
                clip_analyses=analyses,
                output_path=out_video_path,
                owner_message=campaign.request_text,
            )
            dur = time.perf_counter() - t0
            record_step_cost(db, campaign.id, "quality", render_seconds=dur)
            if quality_report.unfixable_failure:
                raise RuntimeError(
                    f"Unfixable quality gate failure: {[g.name for g in quality_report.gates if not g.passed]}"
                )
            return {
                "report": quality_report.model_dump(),
                "video_path": str(final_rendered),
            }

        quality_out = execute_step(
            db, campaign, "quality", "QUALITY_CHECK", _action_quality, max_retries, backoff_base_s
        )
        quality_report = QualityReport.model_validate(quality_out["report"])
        final_video_path = Path(quality_out["video_path"])

        # Persist Video & Update Campaign
        size_bytes = final_video_path.stat().st_size if final_video_path.exists() else 0
        video = db.query(Video).filter(Video.campaign_id == campaign.id, Video.version == 1).first()
        if not video:
            video = Video(
                campaign_id=campaign.id,
                version=1,
                path=str(final_video_path),
                quality_report_json=quality_report.model_dump(),
                size_bytes=size_bytes,
                duration_s=plan_result.target_duration_s,
            )
            db.add(video)
            db.flush()
        else:
            video.path = str(final_video_path)
            video.quality_report_json = quality_report.model_dump()
            video.size_bytes = size_bytes
            video.duration_s = plan_result.target_duration_s

        campaign.plan_json = plan_result.model_dump()
        campaign.template = plan_result.template
        campaign.state = "AWAITING_APPROVAL"
        if conversation:
            conversation.state = ConversationState.AWAITING_APPROVAL
        increment_monthly_usage(db, business.id)
        db.commit()

        # Deliver preview to owner
        from app.storage.signed_urls import generate_signed_video_url

        preview_url = generate_signed_video_url(video.id)
        caption = "Ye lijiye aapki Reel. Sahi hai to OK likhiye. Badlav chahiye to likhiye: 'price 129', 'chhota karo', 'naya hook'."
        provider.send_video(business.phone_e164, preview_url, caption=caption)

        return video

    except Exception as e:
        logger.error(f"Campaign {campaign.id} execution failed: {e}", exc_info=True)
        campaign.state = "FAILED"
        if conversation:
            conversation.state = ConversationState.READY
        db.commit()
        provider.send_text(business.phone_e164, copy.GENERIC_ERROR)
        return None
