"""Simulated end-to-end campaign conversation test: clips -> preview -> revision -> new preview -> ok -> final."""


import pytest

from app.conversation.handlers import handle_inbound_message
from app.conversation.state_machine import ConversationState
from app.llm.client import FakeLLMClient
from app.llm.schemas import ClipAnalysis, Moment, Plan, PlanResult, RevisionRequest
from app.messaging.base import FakeMessagingProvider
from app.models.base import SessionLocal
from app.models.entities import Business, Campaign, Conversation, MediaAsset, MenuItem, Video


@pytest.fixture(autouse=True)
def clean_db() -> None:
    """Clean test tables before and after each test."""
    db = SessionLocal()
    try:
        db.query(Video).delete()
        db.query(Campaign).delete()
        db.query(MediaAsset).delete()
        db.query(MenuItem).delete()
        db.query(Conversation).delete()
        db.query(Business).delete()
        db.commit()

    finally:
        db.close()


def test_simulated_conversation_clips_to_final_flow() -> None:
    """Test full WhatsApp loop: 3 clips -> preview -> 'price 129' -> new preview -> 'ok' -> final video."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919876543210"

    biz = Business(
        phone_e164=phone,
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="Near Metro Pillar 42",
        brand_hex="#FF5722",
    )
    db.add(biz)
    db.flush()

    # Add verified menu items so quality gates pass
    db.add(MenuItem(business_id=biz.id, name="Veg Momo", price_inr=99, is_active=True))
    db.add(MenuItem(business_id=biz.id, name="Special Tandoori Momo", price_inr=129, is_active=True))

    conv = Conversation(business_id=biz.id, state=ConversationState.READY)
    db.add(conv)
    db.commit()

    fixture1 = "tests/fixtures/synthetic/clip1_sharp.mp4"
    fixture2 = "tests/fixtures/synthetic/clip2_blurred.mp4"
    fixture3 = "tests/fixtures/synthetic/clip3_dark.mp4"

    def _canned_llm(prompt: str, schema: type) -> object:
        if schema == ClipAnalysis:
            cid = 1
            if "clip 2" in prompt or "clip_id 2" in prompt:
                cid = 2
            elif "clip 3" in prompt or "clip_id 3" in prompt:
                cid = 3
            return ClipAnalysis(
                clip_id=cid,
                moments=[
                    Moment(
                        t_start=0.0,
                        t_end=3.0,
                        appeal=9,
                        sharpness=9,
                        lighting=8,
                        has_food=True,
                        has_person=False,
                        tag="steam close-up",
                    )
                ],
                overall_note="appetising hot momo",
            )
        if schema in (Plan, PlanResult):
            plan = Plan(
                template="offer",
                target_duration_s=14.0,
                segments=[
                    {"clip_id": 1, "start": 0.0, "end": 2.0},
                    {"clip_id": 2, "start": 0.0, "end": 2.0},
                    {"clip_id": 3, "start": 0.0, "end": 2.0},
                ],
                hook_text="Khaas momo offer!",
                on_screen_lines=["Garam garam momo", "Best taste campus mein"],
                offer_text="Special Offer",
                price_inr=99,
                call_to_action="Aaj hi visit karein",
                caption="Aapke favourite momos at unbeatable price! #foodie",
                hashtags=["#delhi", "#momo", "#offer", "#streetfood", "#foodlover"],
                language="hinglish",
            )
            return PlanResult(root=plan) if schema == PlanResult else plan

        if schema == RevisionRequest:
            if "129" in prompt:
                return RevisionRequest(price_inr=129)
            if "ok" in prompt.lower() or "approve" in prompt.lower():
                return RevisionRequest(approve=True)
            return RevisionRequest(unclear=True)

        raise ValueError(f"Unexpected schema: {schema}")

    fake_llm = FakeLLMClient(canned_responses=_canned_llm)

    # -------------------------------------------------------------
    # Step 1: Owner sends 3 clips within 60s
    # -------------------------------------------------------------
    handle_inbound_message(db, biz, conv, "Momo offer", fixture1, provider, llm_client=fake_llm, auto_process=False)
    handle_inbound_message(db, biz, conv, None, fixture2, provider, llm_client=fake_llm, auto_process=False)
    # Third clip triggers processing
    handle_inbound_message(db, biz, conv, None, fixture3, provider, llm_client=fake_llm, auto_process=True)

    # Verify campaign created and media grouped
    campaign = db.query(Campaign).filter(Campaign.business_id == biz.id).first()
    assert campaign is not None
    assert len(campaign.videos) >= 1
    assert conv.state == ConversationState.AWAITING_APPROVAL

    # Check preview video message was sent
    preview_msgs = [m for m in provider.sent_messages if m.get("type") == "video"]
    assert len(preview_msgs) == 1
    assert "Ye lijiye aapki Reel" in preview_msgs[0]["caption"]
    assert "/videos/" in preview_msgs[0]["video_url"]
    assert "sig=" in preview_msgs[0]["video_url"]
    assert "expires=" in preview_msgs[0]["video_url"]

    # -------------------------------------------------------------
    # Step 2: Owner sends revision request "price 129"
    # -------------------------------------------------------------
    handle_inbound_message(db, biz, conv, "price 129", None, provider, llm_client=fake_llm)

    db.refresh(campaign)
    assert campaign.revision_count == 1
    assert campaign.plan_json["price_inr"] == 129
    assert conv.state == ConversationState.AWAITING_APPROVAL

    # Check new preview video was sent
    preview_msgs = [m for m in provider.sent_messages if m.get("type") == "video"]
    assert len(preview_msgs) == 2
    assert "Ye lijiye aapki nayi Reel" in preview_msgs[1]["caption"]

    # -------------------------------------------------------------
    # Step 3: Owner sends "ok" (approval)
    # -------------------------------------------------------------
    handle_inbound_message(db, biz, conv, "ok", None, provider, llm_client=fake_llm)

    db.refresh(campaign)
    db.refresh(conv)
    assert campaign.state == "APPROVED"
    assert conv.state == ConversationState.READY

    # Check final video delivered with caption + hashtags
    all_videos = [m for m in provider.sent_messages if m.get("type") == "video"]
    assert len(all_videos) == 3
    final_msg = all_videos[2]
    assert "Instagram par post karte waqt" in final_msg["caption"]
    assert "#delhi" in final_msg["caption"]
    assert "#momo" in final_msg["caption"]

    db.close()
