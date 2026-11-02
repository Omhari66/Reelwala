"""Tests for menu photo extraction and owner confirmation flow."""

from pathlib import Path

import pytest

from app.conversation import copy
from app.conversation.handlers import extract_menu_from_image, handle_inbound_message
from app.conversation.state_machine import ConversationState
from app.llm.client import FakeLLMClient
from app.llm.schemas import MenuExtraction
from app.messaging.base import FakeMessagingProvider
from app.models.base import SessionLocal
from app.models.entities import Business, Conversation, MenuItem


@pytest.fixture(autouse=True)
def clean_db() -> None:
    """Clean test tables before and after each test."""
    db = SessionLocal()
    try:
        db.query(MenuItem).delete()
        db.query(Conversation).delete()
        db.query(Business).delete()
        db.commit()
    finally:
        db.close()


def test_extract_menu_from_image_unit(tmp_path: Path) -> None:
    """Unit test for extract_menu_from_image using FakeLLMClient."""
    fake_img = tmp_path / "menu.jpg"
    fake_img.write_bytes(b"dummy image bytes")

    canned = {
        "items": [
            {"name": "Veg Steamed Momo", "price_inr": 60},
            {"name": "Chicken Fried Momo", "price_inr": 100},
            {"name": "Special Thali", "price_inr": None},
        ],
        "uncertain": ["Special Thali"],
    }
    llm = FakeLLMClient(canned_responses={MenuExtraction: canned})

    result = extract_menu_from_image(fake_img, llm_client=llm)
    assert isinstance(result, MenuExtraction)
    assert len(result.items) == 3
    assert result.items[0].name == "Veg Steamed Momo"
    assert result.items[0].price_inr == 60
    assert result.uncertain == ["Special Thali"]

    # Verify prompt used
    assert len(llm.call_history) == 1
    assert "menu_extract_v1" in llm.call_history[0]["prompt"] or "Indian menus" in llm.call_history[0]["prompt"]


def test_menu_photo_conversation_and_owner_confirmation(tmp_path: Path) -> None:
    """End-to-end conversation test: menu photo sent in MENU_SETUP, items extracted and confirmed with YES."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919876543210"

    biz = Business(phone_e164=phone, name="Taste of Tibet", language="hinglish")
    db.add(biz)
    db.flush()

    conv = Conversation(business_id=biz.id, state=ConversationState.MENU_SETUP)
    db.add(conv)
    db.commit()

    canned = {
        "items": [
            {"name": "Tandoori Momo", "price_inr": 120},
            {"name": "Kurkure Momo", "price_inr": 140},
        ],
        "uncertain": [],
    }
    llm = FakeLLMClient(canned_responses={MenuExtraction: canned})

    # Step 1: Owner sends photo in MENU_SETUP
    reply1 = handle_inbound_message(
        db=db,
        business=biz,
        conversation=conv,
        text=None,
        media_url="https://api.twilio.com/Media/ME_menu_pic",
        provider=provider,
        llm_client=llm,
    )

    assert conv.state == ConversationState.MENU_SETUP
    assert "Tandoori Momo ₹120" in reply1
    assert "Kurkure Momo ₹140" in reply1
    assert "YES likhiye" in reply1

    # Check items recorded in DB
    items = db.query(MenuItem).filter(MenuItem.business_id == biz.id).all()
    assert len(items) == 2
    assert {it.name for it in items} == {"Tandoori Momo", "Kurkure Momo"}

    # Step 2: Owner confirms with "YES"
    reply2 = handle_inbound_message(
        db=db,
        business=biz,
        conversation=conv,
        text="YES",
        media_url=None,
        provider=provider,
        llm_client=llm,
    )

    assert conv.state == ConversationState.READY
    assert reply2 == copy.READY_NO_CLIPS
    assert "film karein" in reply2

    db.close()
