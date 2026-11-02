"""Signed, expiring URL generator and verifier for public video delivery."""

import hashlib
import hmac
import time

from app.config import settings


def _get_signing_key() -> str:
    """Return secret key used for signing video delivery URLs."""
    return settings.ADMIN_TOKEN or "reelwala-secure-secret-key"


def compute_video_signature(video_id: int, expires_at: int) -> str:
    """Compute HMAC-SHA256 signature for a video ID and expiry timestamp."""
    key = _get_signing_key().encode("utf-8")
    msg = f"{video_id}:{expires_at}".encode("utf-8")
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def generate_signed_video_url(video_id: int, expires_in_seconds: int = 86400) -> str:
    """Generate public signed URL with expiration timestamp for Twilio media delivery."""
    expires_at = int(time.time()) + expires_in_seconds
    sig = compute_video_signature(video_id, expires_at)
    base_url = settings.PUBLIC_BASE_URL.rstrip("/")
    return f"{base_url}/videos/{video_id}?expires={expires_at}&sig={sig}"


def verify_video_signature(video_id: int, expires_at: int, signature: str) -> bool:
    """Verify HMAC signature and check that the link has not expired."""
    current_time = int(time.time())
    if current_time > expires_at:
        return False

    expected_sig = compute_video_signature(video_id, expires_at)
    return hmac.compare_digest(expected_sig, signature)
