"""SQLAlchemy declarative Base and database session helper."""

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Base declarative class for all ORM models."""

    pass


def utcnow() -> datetime:
    """Return current UTC datetime."""
    return datetime.now(timezone.utc)


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency for yielding database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
