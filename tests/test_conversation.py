"""Scripted conversation tests for onboarding, menu setup, commands, and state machine."""

import pytest

from app.conversation import copy
from app.conversation.handlers import handle_inbound_message, parse_typed_menu
from app.conversation.state_machine import ConversationState
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


def test_parse_typed_menu() -> None:
    """Verify parsing single-line, multi-line, and comma-separated menu text."""
    # Comma separated
    p1 = parse_typed_menu("Momo 60, Combo 99, Cold Coffee 50")
    assert p1 == [("Momo", 60), ("Combo", 99), ("Cold Coffee", 50)]

    # Multi-line with colon and currency symbols
    raw_multiline = (
        "1) Veg Steam Momo: ₹60\n"
        "2) Fried Chicken Momo: 120 Rs\n"
        "- Paneer Kurkure Momo - 140/-\n"
    )
    p2 = parse_typed_menu(raw_multiline)
    assert len(p2) == 3
    assert p2[0] == ("Veg Steam Momo", 60)
    assert p2[1] == ("Fried Chicken Momo", 120)
    assert p2[2] == ("Paneer Kurkure Momo", 140)


def test_full_scripted_onboarding_and_menu_setup() -> None:
    """Full scripted conversation walking through onboarding, menu setup, and ready state."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919876543210"

    biz = Business(phone_e164=phone, name="Pending Name")
    db.add(biz)
    db.flush()

    conv = Conversation(business_id=biz.id, state=ConversationState.NEW_USER)
    db.add(conv)
    db.commit()

    # Step 1: Initial greeting
    r1 = handle_inbound_message(db, biz, conv, "Namaste", None, provider)
    assert conv.state == ConversationState.ONBOARDING_NAME
    assert r1 == copy.GREETING
    assert provider.sent_messages[-1]["body"] == copy.GREETING

    # Step 2: Name
    r2 = handle_inbound_message(db, biz, conv, "Chai Sutta Bar", None, provider)
    assert conv.state == ConversationState.ONBOARDING_CATEGORY
    assert biz.name == "Chai Sutta Bar"
    assert r2 == copy.ASK_CATEGORY

    # Step 3: Category
    r3 = handle_inbound_message(db, biz, conv, "2", None, provider)
    assert conv.state == ConversationState.ONBOARDING_LANGUAGE
    assert biz.category == "Café/Restaurant"
    assert r3 == copy.ASK_LANGUAGE

    # Step 4: Language
    r4 = handle_inbound_message(db, biz, conv, "1", None, provider)
    assert conv.state == ConversationState.ONBOARDING_LANDMARK
    assert biz.language == "hinglish"
    assert r4 == copy.ASK_LANDMARK

    # Step 5: Landmark
    r5 = handle_inbound_message(db, biz, conv, "Near North Campus Gate 4", None, provider)
    assert conv.state == ConversationState.ONBOARDING_BRAND_COLOR
    assert biz.landmark == "Near North Campus Gate 4"
    assert r5 == copy.ASK_BRAND_COLOR

    # Step 6: Brand Color
    r6 = handle_inbound_message(db, biz, conv, "1", None, provider)
    assert conv.state == ConversationState.MENU_SETUP
    assert biz.brand_hex == "#FF5722"
    assert r6 == copy.MENU_SETUP

    # Step 7: Typed Menu Items
    r7 = handle_inbound_message(db, biz, conv, "Kulhad Chai 20, Bun Maska 35", None, provider)
    assert conv.state == ConversationState.MENU_SETUP
    assert "Kulhad Chai ₹20" in r7
    assert "Bun Maska ₹35" in r7

    # Verify items recorded in database
    items = db.query(MenuItem).filter(MenuItem.business_id == biz.id).all()
    assert len(items) == 2

    # Step 8: Confirm Menu Items
    r8 = handle_inbound_message(db, biz, conv, "YES", None, provider)
    assert conv.state == ConversationState.READY
    assert r8 == copy.READY_NO_CLIPS
    assert "film karein" in r8

    # Step 9: Message in READY state gives shot list
    r9 = handle_inbound_message(db, biz, conv, "Ab kya karein?", None, provider)
    assert conv.state == ConversationState.READY
    assert r9 == copy.READY_NO_CLIPS

    db.close()


def test_global_commands_help_status_menu_restart_cancel() -> None:
    """Verify global commands function appropriately across conversation states."""
    db = SessionLocal()
    provider = FakeMessagingProvider()
    phone = "+919988776655"

    biz = Business(phone_e164=phone, name="Dosa King", language="hinglish")
    db.add(biz)
    db.flush()

    conv = Conversation(business_id=biz.id, state=ConversationState.ONBOARDING_NAME)
    db.add(conv)
    db.commit()

    # 1. Help
    r_help = handle_inbound_message(db, biz, conv, "help", None, provider)
    assert r_help == copy.HELP_MESSAGE

    # 2. Status during onboarding
    r_stat = handle_inbound_message(db, biz, conv, "status", None, provider)
    assert r_stat == copy.STATUS_ONBOARDING

    # 3. Menu when empty
    r_menu_empty = handle_inbound_message(db, biz, conv, "menu", None, provider)
    assert r_menu_empty == copy.MENU_EMPTY

    # Add item and query menu
    db.add(MenuItem(business_id=biz.id, name="Masala Dosa", price_inr=90, is_active=True))
    db.commit()
    r_menu_items = handle_inbound_message(db, biz, conv, "menu", None, provider)
    assert "Masala Dosa ₹90" in r_menu_items

    # 4. Cancel
    r_cancel = handle_inbound_message(db, biz, conv, "cancel", None, provider)
    assert r_cancel == copy.CANCEL_MESSAGE

    # 5. Restart
    r_restart = handle_inbound_message(db, biz, conv, "restart", None, provider)
    assert conv.state == ConversationState.ONBOARDING_NAME
    assert r_restart == copy.RESTART_CONFIRM

    # 6. Status when READY
    conv.state = ConversationState.READY
    db.commit()
    r_stat_ready = handle_inbound_message(db, biz, conv, "status", None, provider)
    assert r_stat_ready == copy.STATUS_READY

    db.close()
