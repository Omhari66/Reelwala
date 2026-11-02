"""Tests for serving videos via signed, expiring URLs."""

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.base import SessionLocal
from app.models.entities import Business, Campaign, Video
from app.storage.signed_urls import compute_video_signature, generate_signed_video_url


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_db() -> None:
    """Clean test tables before and after each test."""
    db = SessionLocal()
    try:
        db.query(Video).delete()
        db.query(Campaign).delete()
        db.query(Business).delete()
        db.commit()
    finally:
        db.close()


def test_valid_signed_url_serves_video(client: TestClient, tmp_path: Path) -> None:
    """Valid signed video URL serves the video file with 200 OK and video/mp4 content type."""
    db = SessionLocal()
    biz = Business(phone_e164="+919876543210", name="Momo Stall")
    db.add(biz)
    db.flush()

    camp = Campaign(business_id=biz.id, state="DONE")
    db.add(camp)
    db.flush()

    vid_file = tmp_path / "test_reel.mp4"
    vid_file.write_bytes(b"\x00\x00\x00 ftypisom" + b"video data stream")

    video = Video(
        campaign_id=camp.id,
        version=1,
        path=str(vid_file),
        duration_s=15.0,
        size_bytes=len(vid_file.read_bytes()),
    )
    db.add(video)
    db.commit()
    vid_id = video.id
    db.close()

    # Generate signed URL
    signed_url = generate_signed_video_url(vid_id, expires_in_seconds=3600)
    # Extract path and query from signed_url
    path_and_query = signed_url.replace("https://example.com", "")

    resp = client.get(path_and_query)
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "video/mp4"
    assert resp.content == vid_file.read_bytes()


def test_expired_signed_url_returns_403(client: TestClient, tmp_path: Path) -> None:
    """Expired timestamp in signed URL returns HTTP 403 Forbidden."""
    db = SessionLocal()
    biz = Business(phone_e164="+919876543210", name="Momo Stall")
    db.add(biz)
    db.flush()

    camp = Campaign(business_id=biz.id, state="DONE")
    db.add(camp)
    db.flush()

    vid_file = tmp_path / "test_reel.mp4"
    vid_file.write_bytes(b"dummy")

    video = Video(campaign_id=camp.id, version=1, path=str(vid_file))
    db.add(video)
    db.commit()
    vid_id = video.id
    db.close()

    # Expired 60 seconds ago
    past_expires = int(time.time()) - 60
    sig = compute_video_signature(vid_id, past_expires)

    resp = client.get(f"/videos/{vid_id}?expires={past_expires}&sig={sig}")
    assert resp.status_code == 403
    assert "Expired" in resp.json()["detail"]


def test_tampered_signature_returns_403(client: TestClient, tmp_path: Path) -> None:
    """Tampered signature query param returns HTTP 403 Forbidden."""
    db = SessionLocal()
    biz = Business(phone_e164="+919876543210", name="Momo Stall")
    db.add(biz)
    db.flush()

    camp = Campaign(business_id=biz.id, state="DONE")
    db.add(camp)
    db.flush()

    vid_file = tmp_path / "test_reel.mp4"
    vid_file.write_bytes(b"dummy")

    video = Video(campaign_id=camp.id, version=1, path=str(vid_file))
    db.add(video)
    db.commit()
    vid_id = video.id
    db.close()

    future_expires = int(time.time()) + 3600
    bad_sig = "bad_signature_hexdigest_abc123"

    resp = client.get(f"/videos/{vid_id}?expires={future_expires}&sig={bad_sig}")
    assert resp.status_code == 403
    assert "Expired or invalid" in resp.json()["detail"]


def test_nonexistent_video_returns_404(client: TestClient) -> None:
    """Valid signature for non-existent video ID returns HTTP 404 Not Found."""
    fake_vid_id = 99999
    future_expires = int(time.time()) + 3600
    sig = compute_video_signature(fake_vid_id, future_expires)

    resp = client.get(f"/videos/{fake_vid_id}?expires={future_expires}&sig={sig}")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Video not found"
