"""Test ORM models and database operations."""

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base
from app.models.entities import Business, Campaign, CampaignStep


@pytest.fixture
def db_session() -> Session:
    """Provide an in-memory SQLite database session for unit tests."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_insert_and_read_business_campaign_step(db_session: Session) -> None:
    """Test inserting a business, campaign, and step and reading them back."""
    # 1. Insert business
    biz = Business(
        phone_e164="+919876543210",
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="Near North Gate",
        brand_hex="#FF5722",
    )
    db_session.add(biz)
    db_session.commit()
    db_session.refresh(biz)
    assert biz.id is not None

    # 2. Insert campaign
    camp = Campaign(
        business_id=biz.id,
        state="CREATED",
        request_text="Special fried momo combo 99",
        template="offer",
        plan_json={"target_duration_s": 15},
    )
    db_session.add(camp)
    db_session.commit()
    db_session.refresh(camp)
    assert camp.id is not None

    # 3. Insert campaign step
    step = CampaignStep(
        campaign_id=camp.id,
        name="analyse",
        status="done",
        output_json={"clarity": "good"},
        attempts=1,
    )
    db_session.add(step)
    db_session.commit()
    db_session.refresh(step)
    assert step.id is not None

    # 4. Query back and verify relationships
    stmt = select(Business).where(Business.phone_e164 == "+919876543210")
    retrieved_biz = db_session.scalar(stmt)
    assert retrieved_biz is not None
    assert retrieved_biz.name == "Tibetan Momo Corner"
    assert len(retrieved_biz.campaigns) == 1

    retrieved_camp = retrieved_biz.campaigns[0]
    assert retrieved_camp.template == "offer"
    assert len(retrieved_camp.steps) == 1

    retrieved_step = retrieved_camp.steps[0]
    assert retrieved_step.name == "analyse"
    assert retrieved_step.status == "done"
    assert retrieved_step.output_json == {"clarity": "good"}
