"""Tests for persistent job orchestrator (T5.1): retries, resumption, step outputs, and FAILED handling."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.conversation import copy
from app.conversation.state_machine import ConversationState
from app.llm.client import FakeLLMClient
from app.llm.schemas import ClipAnalysis, Moment, Plan, Segment
from app.messaging.base import FakeMessagingProvider
from app.models.base import SessionLocal
from app.models.entities import (
    Business,
    Campaign,
    CampaignStep,
    Conversation,
    MediaAsset,
    MenuItem,
    Video,
)
from app.pipeline.orchestrator import process_campaign
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(autouse=True)
def clean_db() -> None:
    """Clean database before and after each test."""
    db = SessionLocal()
    try:
        db.query(CampaignStep).delete()
        db.query(Video).delete()
        db.query(Campaign).delete()
        db.query(MediaAsset).delete()
        db.query(MenuItem).delete()
        db.query(Conversation).delete()
        db.query(Business).delete()
        db.commit()
    finally:
        db.close()


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips for testing."""
    temp_dir = tmp_path_factory.mktemp("fixtures_orch")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_orchestrator_kills_step_midway_and_resumes_without_reexecuting_completed_steps(
    fixture_clips: list[Path],
    tmp_path: Path,
) -> None:
    """Done when: test kills a step mid-way and the job resumes without redoing completed steps."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919876543210"

    biz = Business(
        phone_e164=phone,
        name="Chai & Samosa Corner",
        category="Food stall",
        language="hinglish",
        landmark="Near Gate 1",
        brand_hex="#FF5722",
    )
    db.add(biz)
    db.flush()

    db.add(MenuItem(business_id=biz.id, name="Special Samosa", price_inr=25, is_active=True))
    conv = Conversation(business_id=biz.id, state=ConversationState.PROCESSING)
    db.add(conv)

    campaign = Campaign(business_id=biz.id, state="CREATED", request_text="Special Samosa 25")
    db.add(campaign)
    db.flush()

    for p in fixture_clips:
        db.add(MediaAsset(business_id=biz.id, campaign_id=campaign.id, kind="video", path=str(p)))
    db.commit()

    fake_llm = FakeLLMClient(
        canned_responses={
            "ClipAnalysis": ClipAnalysis(
                clip_id=1,
                moments=[
                    Moment(t_start=0, t_end=3, appeal=8, sharpness=8, lighting=8, has_food=True, has_person=False, tag="samosa"),
                    Moment(t_start=3, t_end=5, appeal=7, sharpness=7, lighting=7, has_food=True, has_person=False, tag="chai"),
                ],
                overall_note="fresh and hot",
            ),
            "Plan": Plan(
                template="offer",
                target_duration_s=15.0,
                segments=[
                    Segment(clip_id=1, start=0.0, end=2.0),
                    Segment(clip_id=2, start=0.0, end=2.0),
                    Segment(clip_id=3, start=0.0, end=2.0),
                    Segment(clip_id=1, start=2.0, end=4.0),
                    Segment(clip_id=2, start=2.0, end=4.0),
                    Segment(clip_id=3, start=2.0, end=4.0),
                    Segment(clip_id=1, start=0.0, end=3.0),
                ],
                hook_text="Garam Samosa ₹25!",
                on_screen_lines=["Crispy and hot", "Special Chutney"],
                offer_text="₹25",
                price_inr=25,
                call_to_action="Visit Near Gate 1",
                caption="Garam Samosa only ₹25! #samosa",
                hashtags=["#samosa", "#chai", "#offer", "#delhi", "#food"],
                language="hinglish",
            ),
        }
    )

    download_spy = MagicMock()
    original_normalize = __import__("app.pipeline.download", fromlist=["normalize_media_clip"]).normalize_media_clip

    def spy_normalize(*args, **kwargs):
        download_spy()
        return original_normalize(*args, **kwargs)

    # Run 1: Kill mid-way during step 2 ("analyse")
    with patch("app.pipeline.orchestrator.normalize_media_clip", side_effect=spy_normalize):
        with patch("app.pipeline.orchestrator.analyse_clips_parallel", side_effect=RuntimeError("Worker killed mid-way")):
            res1 = process_campaign(
                db=db,
                campaign_id=campaign.id,
                provider=provider,
                llm_client=fake_llm,
                out_base_dir=str(tmp_path / "run1"),
                max_retries=1,
                backoff_base_s=0.0,
            )

    assert res1 is None

    # Verify state after crash
    db.refresh(campaign)
    assert campaign.state == "FAILED"
    step_download = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == "download").first()
    assert step_download is not None
    assert step_download.status == "done"
    assert "clips" in step_download.output_json
    assert download_spy.call_count == len(fixture_clips)

    # Verify step 2 failed
    step_analyse = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == "analyse").first()
    assert step_analyse is not None
    assert step_analyse.status == "failed"

    # Reset spy count to ensure download is not re-executed during resumption
    download_spy.reset_mock()

    # Run 2: Resume campaign - without the error
    res2 = process_campaign(
        db=db,
        campaign_id=campaign.id,
        provider=provider,
        llm_client=fake_llm,
        out_base_dir=str(tmp_path / "run1"),
        max_retries=3,
        backoff_base_s=0.01,
    )

    assert res2 is not None
    assert isinstance(res2, Video)

    # CRITICAL: Step 1 ("download") was skipped and normalize_media_clip was NEVER called again!
    assert download_spy.call_count == 0

    # Verify all 5 steps are now marked "done"
    steps = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id).order_by(CampaignStep.id).all()
    step_names = [s.name for s in steps]
    assert step_names == ["download", "analyse", "plan", "render", "quality"]
    assert all(s.status == "done" for s in steps)

    db.refresh(campaign)
    assert campaign.state == "AWAITING_APPROVAL"

    # Verify preview video was delivered to owner
    videos = [m for m in provider.sent_messages if m.get("type") == "video"]
    assert len(videos) == 1
    assert "OK likhiye" in (videos[0].get("caption") or "")


def test_orchestrator_step_retry_with_backoff(fixture_clips: list[Path], tmp_path: Path) -> None:
    """Test step transient failure on attempt 1, succeeding on attempt 2."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919876543210"

    biz = Business(
        phone_e164=phone,
        name="Chai & Samosa Corner",
        category="Food stall",
        language="hinglish",
        landmark="Near Gate 1",
        brand_hex="#FF5722",
    )
    db.add(biz)
    db.flush()

    db.add(MenuItem(business_id=biz.id, name="Special Samosa", price_inr=25, is_active=True))
    conv = Conversation(business_id=biz.id, state=ConversationState.PROCESSING)
    db.add(conv)

    campaign = Campaign(business_id=biz.id, state="CREATED", request_text="Special Samosa 25")
    db.add(campaign)
    db.flush()

    for p in fixture_clips:
        db.add(MediaAsset(business_id=biz.id, campaign_id=campaign.id, kind="video", path=str(p)))
    db.commit()

    fake_llm = FakeLLMClient(
        canned_responses={
            "ClipAnalysis": ClipAnalysis(
                clip_id=1,
                moments=[
                    Moment(t_start=0, t_end=3, appeal=8, sharpness=8, lighting=8, has_food=True, has_person=False, tag="samosa"),
                    Moment(t_start=3, t_end=5, appeal=7, sharpness=7, lighting=7, has_food=True, has_person=False, tag="chai"),
                ],
                overall_note="fresh and hot",
            ),
            "Plan": Plan(
                template="offer",
                target_duration_s=15.0,
                segments=[
                    Segment(clip_id=1, start=0.0, end=2.0),
                    Segment(clip_id=2, start=0.0, end=2.0),
                    Segment(clip_id=3, start=0.0, end=2.0),
                    Segment(clip_id=1, start=2.0, end=4.0),
                    Segment(clip_id=2, start=2.0, end=4.0),
                    Segment(clip_id=3, start=2.0, end=4.0),
                    Segment(clip_id=1, start=0.0, end=3.0),
                ],
                hook_text="Garam Samosa ₹25!",
                on_screen_lines=["Crispy and hot", "Special Chutney"],
                offer_text="₹25",
                price_inr=25,
                call_to_action="Visit Near Gate 1",
                caption="Garam Samosa only ₹25! #samosa",
                hashtags=["#samosa", "#chai", "#offer", "#delhi", "#food"],
                language="hinglish",
            ),
        }
    )

    attempt_counter = {"count": 0}
    original_plan = __import__("app.pipeline.plan", fromlist=["plan_ad_campaign"]).plan_ad_campaign

    def flaky_plan(*args, **kwargs):
        attempt_counter["count"] += 1
        if attempt_counter["count"] == 1:
            raise ConnectionError("Transient network timeout to LLM")
        return original_plan(*args, **kwargs)

    with patch("app.pipeline.orchestrator.plan_ad_campaign", side_effect=flaky_plan):
        video = process_campaign(
            db=db,
            campaign_id=campaign.id,
            provider=provider,
            llm_client=fake_llm,
            out_base_dir=str(tmp_path / "flaky"),
            max_retries=3,
            backoff_base_s=0.01,
        )

    assert video is not None
    step_plan = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == "plan").first()
    assert step_plan is not None
    assert step_plan.status == "done"
    assert step_plan.attempts == 2


def test_orchestrator_max_retries_exhaustion_notifies_owner(fixture_clips: list[Path], tmp_path: Path) -> None:
    """Test step exhausting 3 retries sets state FAILED and notifies owner."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919876543210"

    biz = Business(phone_e164=phone, name="Samosa Corner")
    db.add(biz)
    db.flush()

    conv = Conversation(business_id=biz.id, state=ConversationState.PROCESSING)
    db.add(conv)

    campaign = Campaign(business_id=biz.id, state="CREATED")
    db.add(campaign)
    db.flush()

    for p in fixture_clips:
        db.add(MediaAsset(business_id=biz.id, campaign_id=campaign.id, kind="video", path=str(p)))
    db.commit()

    with patch("app.pipeline.orchestrator.analyse_clips_parallel", side_effect=RuntimeError("Persistent LLM outage")):
        video = process_campaign(
            db=db,
            campaign_id=campaign.id,
            provider=provider,
            out_base_dir=str(tmp_path / "failed"),
            max_retries=3,
            backoff_base_s=0.01,
        )

    assert video is None
    db.refresh(campaign)
    assert campaign.state == "FAILED"

    db.refresh(conv)
    assert conv.state == ConversationState.READY

    step_analyse = db.query(CampaignStep).filter(CampaignStep.campaign_id == campaign.id, CampaignStep.name == "analyse").first()
    assert step_analyse is not None
    assert step_analyse.status == "failed"
    assert step_analyse.attempts == 3

    # Check owner received generic error message
    error_texts = [m["body"] for m in provider.sent_messages if m.get("body") == copy.GENERIC_ERROR]
    assert len(error_texts) == 1

