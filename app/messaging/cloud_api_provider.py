"""Meta Cloud API WhatsApp messaging provider stub."""

from app.messaging.base import MessagingProvider


class MetaCloudApiProvider(MessagingProvider):
    """Stub implementation for Meta WhatsApp Cloud API."""

    def send_text(self, to_phone: str, message: str) -> str:
        """Send a plain text message via Meta Cloud API."""
        raise NotImplementedError

    def send_video(self, to_phone: str, video_url: str, caption: str | None = None) -> str:
        """Send a video via Meta Cloud API."""
        raise NotImplementedError
