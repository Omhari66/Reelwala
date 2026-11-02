"""Twilio WhatsApp messaging provider implementation."""

from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.messaging.base import MessagingProvider


class TwilioProvider(MessagingProvider):
    """Twilio WhatsApp messaging provider using official REST API."""

    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        whatsapp_from: str | None = None,
    ) -> None:
        self.account_sid = account_sid or settings.TWILIO_ACCOUNT_SID
        self.auth_token = auth_token or settings.TWILIO_AUTH_TOKEN
        self.whatsapp_from = whatsapp_from or settings.TWILIO_WHATSAPP_FROM
        self.api_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"

    def _normalize_phone(self, phone: str) -> str:
        """Ensure phone number has whatsapp: prefix for WhatsApp API calls."""
        cleaned = phone.strip()
        if cleaned.startswith("whatsapp:"):
            return cleaned
        return f"whatsapp:{cleaned}"

    def send_text(self, to_phone: str, message: str) -> str:
        """Send a plain text message via Twilio WhatsApp API."""
        payload = {
            "From": self._normalize_phone(self.whatsapp_from),
            "To": self._normalize_phone(to_phone),
            "Body": message,
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                self.api_url,
                data=payload,
                auth=(self.account_sid, self.auth_token),
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return str(data.get("sid", ""))

    def send_video(self, to_phone: str, video_url: str, caption: str | None = None) -> str:
        """Send a video with optional caption via Twilio WhatsApp API."""
        payload = {
            "From": self._normalize_phone(self.whatsapp_from),
            "To": self._normalize_phone(to_phone),
            "MediaUrl": video_url,
        }
        if caption:
            payload["Body"] = caption

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                self.api_url,
                data=payload,
                auth=(self.account_sid, self.auth_token),
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return str(data.get("sid", ""))

    def download_media(self, media_url: str, target_path: str) -> str:
        """Download media attachment from Twilio with HTTP Basic Auth and redirect handling."""
        dest = Path(target_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(follow_redirects=True, timeout=60.0) as client:
            # Twilio media endpoints require HTTP Basic Auth
            with client.stream(
                "GET",
                media_url,
                auth=(self.account_sid, self.auth_token),
            ) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=65536):
                        f.write(chunk)

        return str(dest)
