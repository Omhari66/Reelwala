"""Usage counting, per-business concurrency locking, and media limit verification."""

import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.models.base import utcnow
from app.models.entities import Campaign, UsageCounter
from app.pipeline.ffmpeg_utils import run_ffprobe

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_VIDEO_DURATION_S = 60.0  # 60 seconds

BUSY_STATES = {
    "DOWNLOADING",
    "ANALYSING",
    "PLANNING",
    "RENDERING",
    "QUALITY_CHECK",
}


def get_current_month_str() -> str:
    """Return current month in YYYY-MM format."""
    return utcnow().strftime("%Y-%m")


def get_monthly_usage(db: Session, business_id: int, month_str: str | None = None) -> int:
    """Get the video generation count for a business in the specified month."""
    month = month_str or get_current_month_str()
    record = (
        db.query(UsageCounter)
        .filter(UsageCounter.business_id == business_id, UsageCounter.month == month)
        .first()
    )
    return record.count if record else 0


def increment_monthly_usage(db: Session, business_id: int, month_str: str | None = None) -> int:
    """Increment and return the video count for a business in the specified month."""
    month = month_str or get_current_month_str()
    record = (
        db.query(UsageCounter)
        .filter(UsageCounter.business_id == business_id, UsageCounter.month == month)
        .first()
    )
    if not record:
        record = UsageCounter(business_id=business_id, month=month, count=1)
        db.add(record)
    else:
        record.count += 1
    db.commit()
    db.refresh(record)
    return record.count


def is_monthly_limit_reached(db: Session, business_id: int) -> bool:
    """Check if the business has reached or exceeded its monthly limit."""
    used = get_monthly_usage(db, business_id)
    return used >= settings.MONTHLY_VIDEO_LIMIT


def is_business_busy(db: Session, business_id: int, exclude_campaign_id: int | None = None) -> bool:
    """Check if the business has another campaign actively executing in the pipeline."""
    query = db.query(Campaign).filter(
        Campaign.business_id == business_id,
        Campaign.state.in_(BUSY_STATES),
    )
    if exclude_campaign_id:
        query = query.filter(Campaign.id != exclude_campaign_id)
    return query.first() is not None


def inspect_media_file(file_path: str | Path, is_video: bool = True) -> tuple[bool, str | None]:
    """Validate uploaded media meets size (<50MB) and duration (<60s) requirements.

    Returns (is_valid, error_code). Error codes: 'too_large', 'too_long', or None.
    """
    path = Path(file_path)
    if not path.is_file():
        return False, "not_found"

    size = path.stat().st_size
    if size > MAX_FILE_SIZE_BYTES:
        return False, "too_large"

    if is_video:
        try:
            res = run_ffprobe(
                [
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(path),
                ]
            )
            dur = float(res.stdout.strip())
            if dur > MAX_VIDEO_DURATION_S:
                return False, "too_long"
        except Exception as e:
            logger.warning(f"Failed to inspect media duration for {path}: {e}")

    return True, None
