"""Tests for Twilio messaging provider and webhook endpoint."""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.messaging.twilio_provider import TwilioProvider
from app.messaging.twilio_security import compute_twilio_signature
from app.models.base import SessionLocal
from app.models.entities import Business, Conversation, Message


@pytest.fixture
def client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_db() -> None:
    """Clean test tables before and after each test."""
    db = SessionLocal()
    try:
        db.query(Message).delete()
        db.query(Conversation).delete()
        db.query(Business).delete()
        db.commit()
    finally:
        db.close()


def test_signature_failure_returns_403(client: TestClient) -> None:
    """Missing or invalid Twilio signature must return HTTP 403."""
    payload = {
        "MessageSid": "SM99999",
        "From": "whatsapp:+919876543210",
        "Body": "Hello",
    }
    # 1. No signature header
    resp_no_sig = client.post("/webhooks/twilio", data=payload)
    assert resp_no_sig.status_code == 403
    assert resp_no_sig.json()["detail"] == "Invalid Twilio signature"

    # 2. Invalid signature header
    headers = {"X-Twilio-Signature": "invalid_sig_abc123"}
    resp_bad_sig = client.post("/webhooks/twilio", data=payload, headers=headers)
    assert resp_bad_sig.status_code == 403


def test_valid_signature_processes_and_saves_inbound_message(client: TestClient) -> None:
    """Valid signature processes inbound text message and saves to database."""
    test_auth_token = "test_auth_token_secret_123"
    with patch.object(settings, "TWILIO_AUTH_TOKEN", test_auth_token), \
         patch("app.messaging.twilio_provider.TwilioProvider.send_text", return_value="SM_mock_sid"):
        url = "http://testserver/webhooks/twilio"
        payload = {
            "MessageSid": "SM_valid_101",
            "From": "whatsapp:+919876543210",
            "ProfileName": "Chai Point",
            "Body": "Menu update: Samosa 20",
            "NumMedia": "0",
        }
        sig = compute_twilio_signature(url, payload, test_auth_token)
        headers = {"X-Twilio-Signature": sig}

        resp = client.post("/webhooks/twilio", data=payload, headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "received"
        assert data["message_sid"] == "SM_valid_101"

        # Check DB persistence
        db = SessionLocal()
        try:
            msg = db.query(Message).filter(Message.provider_msg_id == "SM_valid_101").first()
            assert msg is not None
            assert msg.body == "Menu update: Samosa 20"
            assert msg.type == "text"
            assert msg.direction == "in"

            biz = db.query(Business).filter(Business.phone_e164 == "+919876543210").first()
            assert biz is not None
            assert biz.name == "Chai Point"
        finally:
            db.close()


def test_duplicate_message_ignored(client: TestClient) -> None:
    """Duplicate provider_msg_id should return 200 OK with duplicate notice and not re-create."""
    test_auth_token = "test_auth_token_secret_123"
    with patch.object(settings, "TWILIO_AUTH_TOKEN", test_auth_token), \
         patch("app.messaging.twilio_provider.TwilioProvider.send_text", return_value="SM_mock_sid"):
        url = "http://testserver/webhooks/twilio"
        payload = {
            "MessageSid": "SM_dupe_202",
            "From": "whatsapp:+919876543210",
            "Body": "Pe pe",
            "NumMedia": "0",
        }
        sig = compute_twilio_signature(url, payload, test_auth_token)
        headers = {"X-Twilio-Signature": sig}

        # First call: receives
        resp1 = client.post("/webhooks/twilio", data=payload, headers=headers)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "received"

        # Second call with exact same MessageSid: duplicate ignored
        resp2 = client.post("/webhooks/twilio", data=payload, headers=headers)
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"
        assert resp2.json()["reason"] == "duplicate"

        # Verify only 1 record exists
        db = SessionLocal()
        try:
            count = db.query(Message).filter(Message.provider_msg_id == "SM_dupe_202").count()
            assert count == 1
        finally:
            db.close()


def test_inbound_video_media_message(client: TestClient) -> None:
    """Inbound message with video media attachment parsed correctly as video type."""
    test_auth_token = "test_auth_token_secret_123"
    with patch.object(settings, "TWILIO_AUTH_TOKEN", test_auth_token), \
         patch("app.messaging.twilio_provider.TwilioProvider.send_text", return_value="SM_mock_sid"):
        url = "http://testserver/webhooks/twilio"
        payload = {
            "MessageSid": "MM_video_303",
            "From": "whatsapp:+919876543210",
            "Body": "Tandoori momo preparation",
            "NumMedia": "1",
            "MediaUrl0": "https://api.twilio.com/Media/ME999",
            "MediaContentType0": "video/mp4",
        }
        sig = compute_twilio_signature(url, payload, test_auth_token)
        headers = {"X-Twilio-Signature": sig}

        resp = client.post("/webhooks/twilio", data=payload, headers=headers)
        assert resp.status_code == 200
        assert resp.json()["type"] == "video"

        db = SessionLocal()
        try:
            msg = db.query(Message).filter(Message.provider_msg_id == "MM_video_303").first()
            assert msg is not None
            assert msg.type == "video"
            assert msg.media_id == "https://api.twilio.com/Media/ME999"
        finally:
            db.close()


def test_webhook_onboarding_conversation_integration(client: TestClient) -> None:
    """Simulate user interacting with the webhook through multiple messages."""
    test_auth_token = "test_auth_token_secret_123"
    with patch.object(settings, "TWILIO_AUTH_TOKEN", test_auth_token), \
         patch("app.messaging.twilio_provider.TwilioProvider.send_text", return_value="SM_mock_sid"):
        url = "http://testserver/webhooks/twilio"
        # 1. First message
        p1 = {"MessageSid": "SM_step_1", "From": "whatsapp:+919111222333", "Body": "Hi", "NumMedia": "0"}
        sig1 = compute_twilio_signature(url, p1, test_auth_token)
        r1 = client.post("/webhooks/twilio", data=p1, headers={"X-Twilio-Signature": sig1})
        assert r1.status_code == 200
        assert "Namaste" in r1.json()["reply"]

        # 2. Second message: Name
        p2 = {"MessageSid": "SM_step_2", "From": "whatsapp:+919111222333", "Body": "Burger Hub", "NumMedia": "0"}
        sig2 = compute_twilio_signature(url, p2, test_auth_token)
        r2 = client.post("/webhooks/twilio", data=p2, headers={"X-Twilio-Signature": sig2})
        assert r2.status_code == 200
        assert "Kaunsa business hai?" in r2.json()["reply"]



def test_twilio_provider_send_text() -> None:
    """TwilioProvider sends text via API and returns message SID."""
    provider = TwilioProvider(
        account_sid="ACtest123",
        auth_token="authtok456",
        whatsapp_from="+14155238886",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "SM_text_sent_1"}

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        sid = provider.send_text("+919876543210", "Aapka reel taiyar hai!")
        assert sid == "SM_text_sent_1"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["To"] == "whatsapp:+919876543210"
        assert kwargs["data"]["From"] == "whatsapp:+14155238886"
        assert kwargs["data"]["Body"] == "Aapka reel taiyar hai!"


def test_twilio_provider_send_video() -> None:
    """TwilioProvider sends video with caption via API and returns message SID."""
    provider = TwilioProvider(
        account_sid="ACtest123",
        auth_token="authtok456",
        whatsapp_from="+14155238886",
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"sid": "MM_video_sent_1"}

    with patch("httpx.Client.post", return_value=mock_resp) as mock_post:
        sid = provider.send_video(
            "+919876543210",
            "https://reelwala.app/videos/preview_1.mp4",
            caption="Check preview",
        )
        assert sid == "MM_video_sent_1"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert kwargs["data"]["MediaUrl"] == "https://reelwala.app/videos/preview_1.mp4"
        assert kwargs["data"]["Body"] == "Check preview"


def test_twilio_provider_download_media(tmp_path: Path) -> None:
    """TwilioProvider streams media content into destination file."""
    provider = TwilioProvider(
        account_sid="ACtest123",
        auth_token="authtok456",
    )
    target_file = tmp_path / "downloads" / "clip.mp4"

    mock_resp = MagicMock()
    mock_resp.iter_bytes.return_value = [b"stream_", b"data_bytes"]

    class MockStreamContext:
        def __enter__(self) -> MagicMock:
            return mock_resp

        def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
            pass

    with patch("httpx.Client.stream", return_value=MockStreamContext()):
        res_path = provider.download_media("https://api.twilio.com/Media/ME1", str(target_file))
        assert Path(res_path).exists()
        assert Path(res_path).read_bytes() == b"stream_data_bytes"
