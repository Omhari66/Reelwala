"""Twilio WhatsApp messaging provider implementation."""

import logging
import time
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.messaging.base import MessagingProvider

logger = logging.getLogger(__name__)

_shared_client: httpx.Client | None = None


def get_shared_client() -> httpx.Client:
    """Return a pooled, keep-alive HTTP client to avoid exhausting sockets on Windows."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.Client(
            timeout=20.0,
            verify=False,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _shared_client


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

    def _post_with_retry(self, payload: dict[str, Any], max_attempts: int = 3) -> dict[str, Any]:
        """Post to Twilio API with connection reuse and exponential backoff retry on 5xx."""
        client = get_shared_client()
        last_exc: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp = client.post(
                    self.api_url,
                    data=payload,
                    auth=(self.account_sid, self.auth_token),
                )
                resp.raise_for_status()
                return resp.json()  # type: ignore[no-any-return]
            except httpx.HTTPStatusError as exc:
                last_exc = exc
                status = exc.response.status_code
                # Retry only on server/gateway errors (500, 502, 503, 504)
                if status in (500, 502, 503, 504) and attempt < max_attempts:
                    logger.warning(
                        f"Twilio API {status} (attempt {attempt}/{max_attempts}). Retrying in {0.5 * attempt}s..."
                    )
                    time.sleep(0.5 * attempt)
                    continue
                raise
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < max_attempts:
                    logger.warning(
                        f"Twilio network error (attempt {attempt}/{max_attempts}): {exc}. Retrying..."
                    )
                    time.sleep(0.5 * attempt)
                    continue
                raise

        if last_exc:
            raise last_exc
        return {}

    def send_text(self, to_phone: str, message: str) -> str:
        """Send a plain text message via Twilio WhatsApp API."""
        payload = {
            "From": self._normalize_phone(self.whatsapp_from),
            "To": self._normalize_phone(to_phone),
            "Body": message,
        }
        data = self._post_with_retry(payload)
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

        data = self._post_with_retry(payload)
        return str(data.get("sid", ""))

    def download_media(self, media_url: str, target_path: str) -> str:
        """Download media attachment from Twilio with HTTP Basic Auth and redirect handling."""
        dest = Path(target_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        with httpx.Client(follow_redirects=True, timeout=60.0, verify=False) as client:
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
