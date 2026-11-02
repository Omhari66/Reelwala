"""Conversation handlers for inbound WhatsApp messages and onboarding flow."""

import re
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.conversation import copy
from app.conversation.intents import (
    detect_command,
    is_cancellation,
    is_confirmation,
)
from app.conversation.state_machine import ConversationState
from app.llm.client import LLMClient
from app.llm.schemas import MenuExtraction, Plan
from app.messaging.base import MessagingProvider
from app.models.entities import Business, Conversation, MenuItem
from app.pipeline.usage import inspect_media_file, is_business_busy, is_monthly_limit_reached
from app.storage.signed_urls import generate_signed_video_url

CATEGORY_MAP = {
    "1": "Food stall",
    "2": "Café/Restaurant",
    "3": "Bakery/Sweets",
    "4": "Other",
}

LANGUAGE_MAP = {
    "1": "hinglish",
    "2": "hindi",
    "3": "english",
}

BRAND_COLOR_MAP = {
    "1": "#FF5722",  # Orange
    "2": "#E53935",  # Red
    "3": "#FBC02D",  # Yellow
    "4": "#43A047",  # Green
    "5": "#1E88E5",  # Blue
    "orange": "#FF5722",
    "red": "#E53935",
    "yellow": "#FBC02D",
    "green": "#43A047",
    "blue": "#1E88E5",
}


def parse_typed_menu(text: str) -> list[tuple[str, int]]:
    """Parse typed menu text like 'Momo 60, Combo 99' or multiline into (name, price_inr) pairs."""
    # Split by newline or comma
    chunks = re.split(r"[\n,]+", text)
    results: list[tuple[str, int]] = []

    for raw in chunks:
        chunk = raw.strip()
        if not chunk:
            continue
        # Match item name followed by price digits (optionally with currency symbols)
        m = re.search(r"^(.*?)(?:[:\-=₹Rs\.]*|\s+)\s*(\d{1,5})\s*(?:rs|inr|₹|/-)?$", chunk, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            # Clean leading/trailing punctuation or numbering like '1)' or '-'
            name = re.sub(r"^[\d\.\-\)\s]+", "", name).strip()
            name = name.rstrip(":-=–— \t")
            price = int(m.group(2))
            if name:
                results.append((name, price))

    return results


def extract_menu_from_image(
    image_path: str | Path,
    llm_client: LLMClient | None = None,
) -> MenuExtraction:
    """Extract menu items and prices from a menu photo using vision LLM."""
    from app.llm.client import get_llm_client

    client = llm_client or get_llm_client()
    prompt_file = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "menu_extract_v1.md"
    prompt = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else "Extract menu items and prices."

    return client.generate_json(
        prompt=prompt,
        schema=MenuExtraction,
        images=[str(image_path)],
    )


def handle_inbound_message(
    db: Session,
    business: Business,
    conversation: Conversation,
    text: str | None,
    media_url: str | None,
    provider: MessagingProvider,
    llm_client: LLMClient | None = None,
    auto_process: bool = False,
) -> str:
    """Process an inbound WhatsApp message according to the conversation state machine."""
    clean_text = (text or "").strip()

    # 1. Check Global Commands
    cmd = detect_command(clean_text)
    if cmd == "help":
        reply = copy.HELP_MESSAGE
        provider.send_text(business.phone_e164, reply)
        return reply

    if cmd == "status":
        if conversation.state == ConversationState.READY:
            reply = copy.STATUS_READY
        else:
            reply = copy.STATUS_ONBOARDING
        provider.send_text(business.phone_e164, reply)
        return reply

    if cmd == "restart":
        conversation.state = ConversationState.ONBOARDING_NAME
        db.commit()
        reply = copy.RESTART_CONFIRM
        provider.send_text(business.phone_e164, reply)
        return reply

    if is_cancellation(clean_text):
        reply = copy.CANCEL_MESSAGE
        provider.send_text(business.phone_e164, reply)
        return reply

    if cmd == "menu":
        items = db.query(MenuItem).filter(MenuItem.business_id == business.id, MenuItem.is_active.is_(True)).all()
        if not items:
            reply = copy.MENU_EMPTY
        else:
            lines = [f"- {it.name} ₹{it.price_inr}" for it in items]
            reply = "Aapka menu:\n" + "\n".join(lines) + "\n\nNaye items jodne ke liye likhiye: Momo 60, Combo 99"
        provider.send_text(business.phone_e164, reply)
        return reply

    # 2. State-driven processing
    state = conversation.state

    if state == ConversationState.NEW_USER:
        conversation.state = ConversationState.ONBOARDING_NAME
        db.commit()
        reply = copy.GREETING
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.ONBOARDING_NAME:
        business.name = clean_text or "My Food Outlet"
        conversation.state = ConversationState.ONBOARDING_CATEGORY
        db.commit()
        reply = copy.ASK_CATEGORY
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.ONBOARDING_CATEGORY:
        category = CATEGORY_MAP.get(clean_text, clean_text) or "Food stall"
        business.category = category
        conversation.state = ConversationState.ONBOARDING_LANGUAGE
        db.commit()
        reply = copy.ASK_LANGUAGE
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.ONBOARDING_LANGUAGE:
        lang = LANGUAGE_MAP.get(clean_text, "hinglish")
        business.language = lang
        conversation.state = ConversationState.ONBOARDING_LANDMARK
        db.commit()
        reply = copy.ASK_LANDMARK
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.ONBOARDING_LANDMARK:
        business.landmark = clean_text
        conversation.state = ConversationState.ONBOARDING_BRAND_COLOR
        db.commit()
        reply = copy.ASK_BRAND_COLOR
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.ONBOARDING_BRAND_COLOR:
        color = BRAND_COLOR_MAP.get(clean_text.lower(), "#FF5722")
        business.brand_hex = color
        conversation.state = ConversationState.MENU_SETUP
        db.commit()
        reply = copy.MENU_SETUP
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.MENU_SETUP:
        # Check if owner sent a photo of their menu
        if media_url:
            tmp_image = f"data/menu_photos/menu_{business.id}_{uuid.uuid4().hex[:6]}.jpg"
            provider.download_media(media_url, tmp_image)
            extraction = extract_menu_from_image(tmp_image, llm_client=llm_client)

            if extraction.items:
                for it in extraction.items:
                    db.add(MenuItem(business_id=business.id, name=it.name, price_inr=it.price_inr, is_active=True))
                db.commit()

                lines = [f"- {it.name} ₹{it.price_inr if it.price_inr is not None else '?'}" for it in extraction.items]
                summary = "\n".join(lines)
                uncertain_note = ""
                if extraction.uncertain:
                    uncertain_note = f"\n(Uncertain: {', '.join(extraction.uncertain)})"
                reply = copy.CONFIRM_MENU_ITEMS.format(items=summary) + uncertain_note
                provider.send_text(business.phone_e164, reply)
                return reply

        # Check if owner is confirming existing items
        active_items = db.query(MenuItem).filter(MenuItem.business_id == business.id, MenuItem.is_active.is_(True)).all()
        if active_items and is_confirmation(clean_text):
            conversation.state = ConversationState.READY
            db.commit()
            reply = copy.READY_NO_CLIPS
            provider.send_text(business.phone_e164, reply)
            return reply

        # Try to parse typed menu items
        parsed = parse_typed_menu(clean_text)
        if parsed:
            for name, price in parsed:
                db.add(MenuItem(business_id=business.id, name=name, price_inr=price, is_active=True))
            db.commit()

            formatted = "\n".join([f"- {name} ₹{price}" for name, price in parsed])
            reply = copy.CONFIRM_MENU_ITEMS.format(items=formatted)
            provider.send_text(business.phone_e164, reply)
            return reply
        else:
            reply = copy.MENU_SETUP
            provider.send_text(business.phone_e164, reply)
            return reply

    elif state in (ConversationState.READY, ConversationState.PROCESSING):
        # Check if media clips were sent
        if media_url:
            from datetime import timedelta

            from app.models.base import utcnow
            from app.models.entities import Campaign, MediaAsset
            from app.pipeline.orchestrator import process_campaign

            # 1. Monthly limit check
            if is_monthly_limit_reached(db, business.id):
                provider.send_text(business.phone_e164, copy.LIMIT_REACHED)
                return copy.LIMIT_REACHED

            # 2. Concurrency check (per-business sequential lock)
            if is_business_busy(db, business.id):
                provider.send_text(business.phone_e164, copy.JOB_IN_PROGRESS)
                return copy.JOB_IN_PROGRESS

            now = utcnow()
            # 60s debounce: look for active campaign within 60s
            cutoff = now - timedelta(seconds=60)
            campaign = (
                db.query(Campaign)
                .filter(
                    Campaign.business_id == business.id,
                    Campaign.state.in_(["gathering", "CREATED"]),
                    Campaign.created_at >= cutoff,
                )
                .order_by(Campaign.created_at.desc())
                .first()
            )

            is_first_media = False
            if not campaign:
                is_first_media = True
                campaign = Campaign(
                    business_id=business.id,
                    state="gathering",
                    request_text=clean_text or None,
                )
                db.add(campaign)
                db.flush()

            # Record media asset
            kind = "video" if "video" in str(media_url).lower() or ".mp4" in str(media_url).lower() else "image"
            ext = ".mp4" if kind == "video" else ".jpg"
            dest_path = f"data/campaigns/{campaign.id}/uploads/{uuid.uuid4().hex[:8]}{ext}"
            provider.download_media(media_url, dest_path)

            # 3. Media limits check: size <= 50MB, duration <= 60s
            is_valid, err_code = inspect_media_file(dest_path, is_video=(kind == "video"))
            if not is_valid:
                try:
                    Path(dest_path).unlink(missing_ok=True)
                except Exception:
                    pass
                if err_code == "too_large":
                    err_reply = copy.MEDIA_TOO_LARGE
                elif err_code == "too_long":
                    err_reply = copy.MEDIA_TOO_LONG
                else:
                    err_reply = copy.GENERIC_ERROR
                provider.send_text(business.phone_e164, err_reply)
                return err_reply

            asset = MediaAsset(
                business_id=business.id,
                campaign_id=campaign.id,
                kind=kind,
                path=dest_path,
            )
            db.add(asset)
            conversation.state = ConversationState.PROCESSING
            db.commit()

            if is_first_media:
                provider.send_text(business.phone_e164, copy.CLIPS_RECEIVED)

            # In direct execution or test mode, process if requested or multiple clips
            if auto_process:
                process_campaign(db, campaign.id, provider, llm_client=llm_client)

            return copy.CLIPS_RECEIVED

        # Text received without media
        reply = copy.READY_NO_CLIPS
        provider.send_text(business.phone_e164, reply)
        return reply

    elif state == ConversationState.AWAITING_APPROVAL:
        from app.models.entities import Campaign, MediaAsset, Video
        from app.pipeline.orchestrator import build_business_context
        from app.pipeline.quality import run_pipeline_with_quality_autofix
        from app.pipeline.revise import apply_revision, parse_revision_request

        campaign = (
            db.query(Campaign)
            .filter(Campaign.business_id == business.id)
            .order_by(Campaign.created_at.desc())
            .first()
        )
        if not campaign:
            reply = copy.UNKNOWN_MESSAGE
            provider.send_text(business.phone_e164, reply)
            return reply

        # 1. Approval
        if is_confirmation(clean_text):
            campaign.state = "APPROVED"
            conversation.state = ConversationState.READY
            db.commit()

            plan_dict = campaign.plan_json or {}
            caption = plan_dict.get("caption", "Aapka special Reel!")
            hashtags = " ".join(plan_dict.get("hashtags", []))
            latest_vid = (
                db.query(Video)
                .filter(Video.campaign_id == campaign.id)
                .order_by(Video.version.desc())
                .first()
            )

            vid_id = latest_vid.id if latest_vid else 1
            final_url = generate_signed_video_url(vid_id)
            final_caption = (
                f"{caption}\n\n{hashtags}\n\n"
                "Instagram par post karte waqt trending audio chahein to wahin add kar sakte hain. "
                "Next Reel ke liye clips bhej dein!"
            )
            provider.send_video(business.phone_e164, final_url, caption=final_caption)
            return final_caption

        # 2. Revisions
        if campaign.revision_count >= 3:
            reply = copy.REVISION_LIMIT
            provider.send_text(business.phone_e164, reply)
            return reply

        provider.send_text(business.phone_e164, copy.REVISION_STARTED)

        current_plan = Plan.model_validate(campaign.plan_json)
        biz_context = build_business_context(business)
        from app.llm.client import get_llm_client
        client = llm_client or get_llm_client()

        rev_req = parse_revision_request(
            owner_message=clean_text,
            current_plan=current_plan,
            business=biz_context,
            llm_client=client,
        )
        if rev_req.unclear:
            reply = copy.UNKNOWN_MESSAGE
            provider.send_text(business.phone_e164, reply)
            return reply

        assets = db.query(MediaAsset).filter(MediaAsset.campaign_id == campaign.id).all()
        clips_dict = {idx: Path(a.path) for idx, a in enumerate(assets, start=1)}

        from app.pipeline.analyse import analyse_clips_parallel
        clip_items = [(idx, p) for idx, p in clips_dict.items()]
        clip_analyses = analyse_clips_parallel(clip_items, llm_client=llm_client)

        revised_plan, _ = apply_revision(
            current_plan=current_plan,
            revision=rev_req,
            revision_count=campaign.revision_count,
            business=biz_context,
            clip_analyses=clip_analyses,
        )

        new_version = campaign.revision_count + 2
        out_path = Path(f"data/campaigns/{campaign.id}/video_v{new_version}.mp4")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        rendered_vid, q_report = run_pipeline_with_quality_autofix(
            plan=revised_plan,
            business=biz_context,
            clip_paths=clips_dict,
            clip_analyses=clip_analyses,
            output_path=out_path,
            owner_message=campaign.request_text,
        )

        new_vid = Video(
            campaign_id=campaign.id,
            version=new_version,
            path=str(rendered_vid),
            quality_report_json=q_report.model_dump(),
            duration_s=revised_plan.target_duration_s,
        )
        db.add(new_vid)
        campaign.plan_json = revised_plan.model_dump()
        campaign.revision_count += 1
        conversation.state = ConversationState.AWAITING_APPROVAL
        db.commit()

        new_url = generate_signed_video_url(new_vid.id)
        new_caption = "Ye lijiye aapki nayi Reel. Sahi hai to OK likhiye. Badlav chahiye to batayein."
        provider.send_video(business.phone_e164, new_url, caption=new_caption)
        return new_caption

    # Fallback for unknown states or messages
    reply = copy.UNKNOWN_MESSAGE
    provider.send_text(business.phone_e164, reply)
    return reply

