"""Configuration management for Reelwala using pydantic-settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment and .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM Settings
    LLM_PROVIDER: str = "gemini"
    LLM_API_KEY: str = ""
    LLM_MODEL_VISION: str = ""
    LLM_MODEL_TEXT: str = ""

    # Database & Cache
    DATABASE_URL: str = "sqlite:///./dev.db"
    REDIS_URL: str = "redis://localhost:6379/0"

    # Storage
    STORAGE_BACKEND: str = "local"
    STORAGE_PATH: str = "./data"

    # Twilio / Messaging
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"
    PUBLIC_BASE_URL: str = "https://example.com"

    # Security & Operations
    ADMIN_TOKEN: str = "change-me"
    MONTHLY_VIDEO_LIMIT: int = 10
    USD_INR: float = 85.0
    ENABLE_VOICE_NOTES: bool = False


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()


settings = get_settings()
