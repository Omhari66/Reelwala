"""Test health check and application bootstrap."""

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    """Test that /health returns 200 with status ok."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_loaded() -> None:
    """Test that default settings load properly."""
    assert settings.MONTHLY_VIDEO_LIMIT == 10
    assert settings.STORAGE_BACKEND in ("local", "s3")
