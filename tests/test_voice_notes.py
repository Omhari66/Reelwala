"""Tests for optional voice-note handling and transcription behind ENABLE_VOICE_NOTES."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.conversation import copy
from app.conversation.transcribe import transcribe_voice_note
from app.main import app
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


def test_transcribe_voice_note_disabled_returns_none(tmp_path: Path) -> None:
    """When ENABLE_VOICE_NOTES is False, transcribe_voice_note returns None."""
    dummy_audio = tmp_path / "voice.ogg"
    dummy_audio.write_bytes(b"dummy ogg audio")

    with patch.object(settings, "ENABLE_VOICE_NOTES", False):
        result = transcribe_voice_note(dummy_audio)
        assert result is None


def test_inbound_voice_note_when_disabled_replies_with_text_notice(client: TestClient) -> None:
    """When ENABLE_VOICE_NOTES is False, webhook responds asking for text."""
    test_auth_token = "test_auth_token_secret_123"
    with patch.object(settings, "TWILIO_AUTH_TOKEN", test_auth_token):
        with patch.object(settings, "ENABLE_VOICE_NOTES", False):
            url = "http://testserver/webhooks/twilio"
            payload = {
                "MessageSid": "MM_audio_001",
                "From": "whatsapp:+919876543210",
                "NumMedia": "1",
                "MediaUrl0": "https://api.twilio.com/Media/ME_audio_1",
                "MediaContentType0": "audio/ogg",
            }
            sig = compute_twilio_signature(url, payload, test_auth_token)
            headers = {"X-Twilio-Signature": sig}

            resp = client.post("/webhooks/twilio", data=payload, headers=headers)
            assert resp.status_code == 200
            data = resp.json()
            assert data["type"] == "audio"
            assert data["reply"] == copy.VOICE_NOTE_DISABLED


def test_inbound_voice_note_when_enabled_transcribes_and_processes(client: TestClient) -> None:
    """When ENABLE_VOICE_NOTES is True, audio is transcribed and routed to conversation handler."""
    test_auth_token = "test_auth_token_secret_123"
    with patch.object(settings, "TWILIO_AUTH_TOKEN", test_auth_token):
        with patch.object(settings, "ENABLE_VOICE_NOTES", True):
            with patch("app.conversation.transcribe.transcribe_voice_note", return_value="Chai Sutta Corner"):
                url = "http://testserver/webhooks/twilio"
                payload = {
                    "MessageSid": "MM_audio_002",
                    "From": "whatsapp:+919876543210",
                    "NumMedia": "1",
                    "MediaUrl0": "https://api.twilio.com/Media/ME_audio_2",
                    "MediaContentType0": "audio/ogg",
                }
                sig = compute_twilio_signature(url, payload, test_auth_token)
                headers = {"X-Twilio-Signature": sig}

                resp = client.post("/webhooks/twilio", data=payload, headers=headers)
                assert resp.status_code == 200
                data = resp.json()
                assert data["type"] == "audio"
                # First message initializes greeting
                assert "Namaste" in data["reply"]
