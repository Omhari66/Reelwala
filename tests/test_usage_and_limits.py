"""Tests for usage limits, per-business lock, and media limits (T5.2)."""

from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from app.config import settings
from app.conversation import copy
from app.conversation.handlers import handle_inbound_message
from app.conversation.state_machine import ConversationState
from app.messaging.base import FakeMessagingProvider
from app.models.base import SessionLocal
from app.models.entities import Business, Campaign, Conversation, MediaAsset, MenuItem, UsageCounter
from app.pipeline.usage import (
    get_current_month_str,
    get_monthly_usage,
    increment_monthly_usage,
    inspect_media_file,
    is_business_busy,
    is_monthly_limit_reached,
)
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Yield a database session and clean tables before and after."""
    session = SessionLocal()
    try:
        session.query(UsageCounter).delete()
        session.query(Campaign).delete()
        session.query(MediaAsset).delete()
        session.query(MenuItem).delete()
        session.query(Conversation).delete()
        session.query(Business).delete()
        session.commit()
        yield session
    finally:
        session.rollback()
        session.query(UsageCounter).delete()
        session.query(Campaign).delete()
        session.query(MediaAsset).delete()
        session.query(MenuItem).delete()
        session.query(Conversation).delete()
        session.query(Business).delete()
        session.commit()
        session.close()


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips for testing."""
    temp_dir = tmp_path_factory.mktemp("fixtures_limits")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_monthly_usage_counter_and_limit(db: Session) -> None:
    """Test usage counter increments and limit detection."""
    biz = Business(phone_e164="+919876543210", name="Dosa Hub")
    db.add(biz)
    db.flush()

    conv = Conversation(business_id=biz.id, state=ConversationState.READY)
    db.add(conv)
    db.commit()

    month = get_current_month_str()
    assert get_monthly_usage(db, biz.id, month_str=month) == 0
    assert not is_monthly_limit_reached(db, biz.id)

    # Increment up to limit
    for _ in range(settings.MONTHLY_VIDEO_LIMIT - 1):
        increment_monthly_usage(db, biz.id)

    assert get_monthly_usage(db, biz.id) == settings.MONTHLY_VIDEO_LIMIT - 1
    assert not is_monthly_limit_reached(db, biz.id)

    # Hit the limit
    increment_monthly_usage(db, biz.id)
    assert get_monthly_usage(db, biz.id) == settings.MONTHLY_VIDEO_LIMIT
    assert is_monthly_limit_reached(db, biz.id) is True

    # Sending clips when limit reached yields friendly message
    provider = FakeMessagingProvider()
    reply = handle_inbound_message(
        db=db,
        business=biz,
        conversation=conv,
        text="promote masala dosa",
        media_url="tests/fixtures/synthetic/clip1_sharp.mp4",
        provider=provider,
    )
    assert reply == copy.LIMIT_REACHED


def test_per_business_sequential_lock(db: Session) -> None:
    """Test concurrent active campaign blocks new clip ingestion with friendly message."""
    biz = Business(phone_e164="+919876543211", name="Idli Express")
    db.add(biz)
    db.flush()

    conv = Conversation(business_id=biz.id, state=ConversationState.PROCESSING)
    db.add(conv)

    # Active campaign currently rendering
    active_campaign = Campaign(business_id=biz.id, state="RENDERING")
    db.add(active_campaign)
    db.commit()

    assert is_business_busy(db, biz.id) is True

    provider = FakeMessagingProvider()
    reply = handle_inbound_message(
        db=db,
        business=biz,
        conversation=conv,
        text="naya video banao",
        media_url="tests/fixtures/synthetic/clip1_sharp.mp4",
        provider=provider,
    )
    assert reply == copy.JOB_IN_PROGRESS


def test_media_size_limit_rejection(db: Session, tmp_path: Path) -> None:
    """Test media exceeding 50 MB is rejected with friendly message."""
    biz = Business(phone_e164="+919876543212", name="Burger Shack")
    db.add(biz)
    db.flush()
    conv = Conversation(business_id=biz.id, state=ConversationState.READY)
    db.add(conv)
    db.commit()

    sample_file = tmp_path / "large_clip.mp4"
    sample_file.write_bytes(b"dummy")

    with patch("pathlib.Path.stat") as mock_stat:
        st = MagicMock()
        st.st_size = 55 * 1024 * 1024  # 55 MB
        st.st_mode = 33188  # regular file
        mock_stat.return_value = st
        is_valid, err = inspect_media_file(sample_file, is_video=True)
        assert is_valid is False
        assert err == "too_large"

    provider = FakeMessagingProvider()
    with patch("app.conversation.handlers.inspect_media_file", return_value=(False, "too_large")):
        reply = handle_inbound_message(
            db=db,
            business=biz,
            conversation=conv,
            text="special burger",
            media_url="tests/fixtures/synthetic/clip1_sharp.mp4",
            provider=provider,
        )
        assert reply == copy.MEDIA_TOO_LARGE


def test_media_duration_limit_rejection(db: Session, tmp_path: Path) -> None:
    """Test video clip exceeding 60 seconds is rejected with friendly message."""
    biz = Business(phone_e164="+919876543213", name="Pizza Corner")
    db.add(biz)
    db.flush()
    conv = Conversation(business_id=biz.id, state=ConversationState.READY)
    db.add(conv)
    db.commit()

    sample_file = tmp_path / "long_clip.mp4"
    sample_file.write_bytes(b"dummy")

    with patch("app.pipeline.usage.run_ffprobe") as mock_ffprobe:
        mock_res = MagicMock()
        mock_res.stdout = "75.4\n"  # 75.4s > 60s
        mock_ffprobe.return_value = mock_res

        is_valid, err = inspect_media_file(sample_file, is_video=True)
        assert is_valid is False
        assert err == "too_long"

    provider = FakeMessagingProvider()
    with patch("app.conversation.handlers.inspect_media_file", return_value=(False, "too_long")):
        reply = handle_inbound_message(
            db=db,
            business=biz,
            conversation=conv,
            text="pizza offer",
            media_url="tests/fixtures/synthetic/clip1_sharp.mp4",
            provider=provider,
        )
        assert reply == copy.MEDIA_TOO_LONG
