"""Tests for business wipeout script and phone logging masking (T5.4)."""

import logging
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.logging_utils import SensitiveDataFilter, mask_phone
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
from scripts.delete_business import delete_business_data


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Yield a test database session and clean tables."""
    session = SessionLocal()
    try:
        session.query(CampaignStep).delete()
        session.query(Video).delete()
        session.query(Campaign).delete()
        session.query(MediaAsset).delete()
        session.query(MenuItem).delete()
        session.query(Conversation).delete()
        session.query(Business).delete()
        session.commit()
        yield session
    finally:
        session.rollback()
        session.query(CampaignStep).delete()
        session.query(Video).delete()
        session.query(Campaign).delete()
        session.query(MediaAsset).delete()
        session.query(MenuItem).delete()
        session.query(Conversation).delete()
        session.query(Business).delete()
        session.commit()
        session.close()


def test_phone_masking_function() -> None:
    """Test mask_phone keeps only prefix and last 4 digits."""
    assert mask_phone("+919876543210") == "+91******3210"
    assert mask_phone("9876543210") == "******3210"
    assert mask_phone("1234") == "****"
    assert mask_phone("12") == "**"
    assert mask_phone(None) == ""


def test_sensitive_data_logging_filter() -> None:
    """Test SensitiveDataFilter masks phone numbers and API keys in log records."""
    filter_inst = SensitiveDataFilter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Inbound message from +919876543210 with key AIzaSyD98765432101234567890abcdefghijkl",
        args=(),
        exc_info=None,
    )
    filter_inst.filter(record)
    assert "+919876543210" not in record.msg
    assert "3210" in record.msg
    assert "AIzaSyD98765432101234567890abcdefghijkl" not in record.msg
    assert "[REDACTED_KEY]" in record.msg


def test_delete_business_script_purges_db_and_disk(db: Session, tmp_path: Path) -> None:
    """Test delete_business_data removes all files from disk and cascaded DB records."""
    phone = "+919999111122"
    biz = Business(phone_e164=phone, name="To Be Deleted Stall")
    db.add(biz)
    db.flush()

    db.add(MenuItem(business_id=biz.id, name="Test Item", price_inr=50, is_active=True))
    db.add(Conversation(business_id=biz.id))

    camp = Campaign(business_id=biz.id, state="DONE")
    db.add(camp)
    db.flush()

    # Create dummy campaign directory and media files
    camp_dir = Path(f"data/campaigns/{camp.id}")
    camp_dir.mkdir(parents=True, exist_ok=True)
    clip_file = camp_dir / "sample_clip.mp4"
    clip_file.write_bytes(b"dummy clip data")

    db.add(MediaAsset(business_id=biz.id, campaign_id=camp.id, kind="video", path=str(clip_file)))
    db.add(Video(campaign_id=camp.id, version=1, path=str(clip_file)))
    db.commit()

    assert camp_dir.exists()
    assert clip_file.exists()

    # Perform delete
    res = delete_business_data(db, phone_e164=phone)
    assert res["found"] is True
    assert res["deleted"] is True
    assert res["campaigns_count"] == 1

    # Verify on-disk directories and files are gone
    assert not camp_dir.exists()
    assert not clip_file.exists()

    # Verify database records are deleted
    assert db.query(Business).filter(Business.id == biz.id).first() is None
    assert db.query(Campaign).filter(Campaign.business_id == biz.id).first() is None
    assert db.query(MenuItem).filter(MenuItem.business_id == biz.id).first() is None
    assert db.query(Conversation).filter(Conversation.business_id == biz.id).first() is None
    assert db.query(MediaAsset).filter(MediaAsset.business_id == biz.id).first() is None
