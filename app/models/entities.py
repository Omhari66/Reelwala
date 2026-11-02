"""SQLAlchemy ORM models per ARCHITECTURE.md section 3."""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.sqlite import JSON as SQLITE_JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.models.base import Base, utcnow

JsonType = JSON().with_variant(SQLITE_JSON, "sqlite")


class Business(Base):
    """Registered business profile."""

    __tablename__ = "businesses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_e164: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    language: Mapped[str] = mapped_column(String(32), default="hinglish", nullable=False)
    landmark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    brand_hex: Mapped[str] = mapped_column(String(16), default="#FF5722", nullable=False)
    plan: Mapped[str] = mapped_column(String(32), default="free", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    menu_items: Mapped[list["MenuItem"]] = relationship("MenuItem", back_populates="business")
    campaigns: Mapped[list["Campaign"]] = relationship("Campaign", back_populates="business")


class MenuItem(Base):
    """Menu item with price for price verification."""

    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    price_inr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    business: Mapped["Business"] = relationship("Business", back_populates="menu_items")


class Conversation(Base):
    """WhatsApp conversation state tracker."""

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(64), default="NEW_USER", nullable=False)
    last_message_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    messages: Mapped[list["Message"]] = relationship("Message", back_populates="conversation")


class Message(Base):
    """Inbound and outbound messages with provider deduplication."""

    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)  # in | out
    type: Mapped[str] = mapped_column(String(32), default="text", nullable=False)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    provider_msg_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    conversation: Mapped["Conversation"] = relationship("Conversation", back_populates="messages")


class MediaAsset(Base):
    """Raw media clip, image, audio, or menu photo."""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # video | image | audio | menu_photo
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Campaign(Base):
    """Video creation campaign for an owner request."""

    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    state: Mapped[str] = mapped_column(String(64), default="CREATED", nullable=False)
    request_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    template: Mapped[str | None] = mapped_column(String(64), nullable=True)
    plan_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    revision_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    business: Mapped["Business"] = relationship("Business", back_populates="campaigns")
    steps: Mapped[list["CampaignStep"]] = relationship("CampaignStep", back_populates="campaign")
    videos: Mapped[list["Video"]] = relationship("Video", back_populates="campaign")


class CampaignStep(Base):
    """Individual execution step in a campaign pipeline."""

    __tablename__ = "campaign_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="steps")


class Video(Base):
    """Rendered video output version."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    quality_report_json: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)

    campaign: Mapped["Campaign"] = relationship("Campaign", back_populates="videos")


class UsageCounter(Base):
    """Monthly video creation usage tracker."""

    __tablename__ = "usage_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    business_id: Mapped[int] = mapped_column(ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False)
    month: Mapped[str] = mapped_column(String(7), nullable=False)  # YYYY-MM
    count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class CostLog(Base):
    """Per-step compute and token cost log."""

    __tablename__ = "cost_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False)
    step: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    render_seconds: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    est_cost_inr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
