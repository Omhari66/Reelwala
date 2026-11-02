"""Abstract base interface and test fake for messaging providers."""

import uuid
from abc import ABC, abstractmethod
from typing import Any


class MessagingProvider(ABC):
    """Abstract messaging provider interface."""

    @abstractmethod
    def send_text(self, to_phone: str, message: str) -> str:
        """Send a plain text message to a recipient and return provider message ID."""
        raise NotImplementedError

    @abstractmethod
    def send_video(self, to_phone: str, video_url: str, caption: str | None = None) -> str:
        """Send a video with optional caption to a recipient and return provider message ID."""
        raise NotImplementedError

    @abstractmethod
    def download_media(self, media_url: str, target_path: str) -> str:
        """Download media from provider (handling auth) to target_path and return target_path."""
        raise NotImplementedError


class FakeMessagingProvider(MessagingProvider):
    """Test fake recording sent messages and returning mock IDs."""

    def __init__(self) -> None:
        self.sent_messages: list[dict[str, Any]] = []

    def send_text(self, to_phone: str, message: str) -> str:
        """Record outbound text message."""
        msg_id = f"mock_text_{uuid.uuid4().hex[:8]}"
        self.sent_messages.append(
            {
                "id": msg_id,
                "type": "text",
                "to": to_phone,
                "body": message,
            }
        )
        return msg_id

    def send_video(self, to_phone: str, video_url: str, caption: str | None = None) -> str:
        """Record outbound video message."""
        msg_id = f"mock_video_{uuid.uuid4().hex[:8]}"
        self.sent_messages.append(
            {
                "id": msg_id,
                "type": "video",
                "to": to_phone,
                "video_url": video_url,
                "caption": caption,
            }
        )
        return msg_id

    def download_media(self, media_url: str, target_path: str) -> str:
        """Record and fake downloading media to target_path."""
        import shutil
        from pathlib import Path

        p = Path(target_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        src = Path(media_url)
        if src.is_file():
            shutil.copy2(src, p)
        elif not p.exists():
            p.write_bytes(b"fake media content")
        return str(p)


