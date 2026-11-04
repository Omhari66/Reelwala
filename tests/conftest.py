"""Shared pytest fixtures and test environment configuration."""

import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def _isolate_test_environment(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Ensure tests run against fake providers by default rather than real Twilio/APIs."""
    if "test_twilio" not in request.node.nodeid:
        monkeypatch.setattr(settings, "TWILIO_ACCOUNT_SID", None)
        monkeypatch.setattr(settings, "TWILIO_AUTH_TOKEN", None)

