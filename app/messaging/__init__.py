"""Messaging providers package."""

from app.config import settings
from app.messaging.base import FakeMessagingProvider, MessagingProvider
from app.messaging.twilio_provider import TwilioProvider


def get_messaging_provider() -> MessagingProvider:
    """Return configured messaging provider (Twilio or test fake)."""
    if settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN:
        return TwilioProvider()
    return FakeMessagingProvider()


__all__ = [
    "MessagingProvider",
    "FakeMessagingProvider",
    "TwilioProvider",
    "get_messaging_provider",
]
