"""Tests for cost logging and admin jobs dashboard (T5.3)."""

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.llm.client import FakeLLMClient
from app.llm.schemas import ClipAnalysis, Moment, Plan, Segment
from app.main import app
from app.messaging.base import FakeMessagingProvider
from app.models.base import SessionLocal
from app.models.entities import (
    Business,
    Campaign,
    CampaignStep,
    CostLog,
    MediaAsset,
    MenuItem,
    Video,
)
from app.pipeline.cost import compute_cost_inr, record_step_cost
from app.pipeline.orchestrator import process_campaign
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Yield a clean test database session."""
    session = SessionLocal()
    try:
        session.query(CostLog).delete()
        session.query(CampaignStep).delete()
        session.query(Video).delete()
        session.query(Campaign).delete()
        session.query(MediaAsset).delete()
        session.query(MenuItem).delete()
        session.query(Business).delete()
        session.commit()
        yield session
    finally:
        session.rollback()
        session.query(CostLog).delete()
        session.query(CampaignStep).delete()
        session.query(Video).delete()
        session.query(Campaign).delete()
        session.query(MediaAsset).delete()
        session.query(MenuItem).delete()
        session.query(Business).delete()
        session.commit()
        session.close()


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips for testing."""
    temp_dir = tmp_path_factory.mktemp("fixtures_admin")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_cost_calculation_and_recording(db: Session) -> None:
    """Test token and compute cost calculation in INR."""
    # 10,000 in + 2,000 out + 10s render @ rate 85
    # input = 10,000 / 1M * 0.075 * 85 = 0.06375 INR
    # output = 2,000 / 1M * 0.30 * 85 = 0.051 INR
    # render = 10 * 0.002 = 0.02 INR
    # total ~ 0.1348 INR
    cost = compute_cost_inr(input_tokens=10_000, output_tokens=2_000, render_seconds=10.0, usd_inr=85.0)
    assert 0.13 <= cost <= 0.14

    biz = Business(phone_e164="+919999888877", name="Cost Test Cafe")
    db.add(biz)
    db.flush()

    camp = Campaign(business_id=biz.id, state="ANALYSING")
    db.add(camp)
    db.commit()

    entry = record_step_cost(
        db,
        campaign_id=camp.id,
        step="analyse",
        input_tokens=10_000,
        output_tokens=2_000,
        render_seconds=10.0,
    )
    assert entry.id is not None
    assert entry.est_cost_inr == cost
    assert entry.step == "analyse"


def test_admin_jobs_endpoint_auth(db: Session) -> None:
    """Test GET /admin/jobs authentication rules."""
    client = TestClient(app)

    # Missing token -> 422
    resp_no_token = client.get("/admin/jobs")
    assert resp_no_token.status_code == 422

    # Wrong token -> 403
    resp_bad_token = client.get("/admin/jobs?token=invalid_token_123")
    assert resp_bad_token.status_code == 403

    # Valid token -> 200
    resp_ok = client.get(f"/admin/jobs?token={settings.ADMIN_TOKEN}")
    assert resp_ok.status_code == 200
    assert "Campaign Jobs" in resp_ok.text
    assert "No jobs recorded yet." in resp_ok.text


def test_admin_jobs_dashboard_table(db: Session, fixture_clips: list[Path], tmp_path: Path) -> None:
    """Test dashboard table displays campaign id, business, state, duration, cost, and error."""
    provider = FakeMessagingProvider()
    biz = Business(
        phone_e164="+919876543210",
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="Near Metro Pillar 42",
        brand_hex="#FF5722",
    )
    db.add(biz)
    db.flush()

    db.add(MenuItem(business_id=biz.id, name="Veg Momo", price_inr=99, is_active=True))
    camp = Campaign(business_id=biz.id, state="CREATED", request_text="Special Veg Momo 99")
    db.add(camp)
    db.flush()

    for p in fixture_clips:
        db.add(MediaAsset(business_id=biz.id, campaign_id=camp.id, kind="video", path=str(p)))
    db.commit()

    fake_llm = FakeLLMClient(
        canned_responses={
            "ClipAnalysis": ClipAnalysis(
                clip_id=1,
                moments=[
                    Moment(t_start=0, t_end=3, appeal=8, sharpness=8, lighting=8, has_food=True, has_person=False, tag="momo"),
                    Moment(t_start=3, t_end=5, appeal=7, sharpness=7, lighting=7, has_food=True, has_person=False, tag="serving"),
                ],
                overall_note="appetising and clean",
            ),
            "Plan": Plan(
                template="offer",
                target_duration_s=15.0,
                segments=[
                    Segment(clip_id=1, start=0.0, end=2.0),
                    Segment(clip_id=2, start=0.0, end=2.0),
                    Segment(clip_id=3, start=0.0, end=2.0),
                    Segment(clip_id=1, start=2.0, end=4.0),
                    Segment(clip_id=2, start=2.0, end=4.0),
                    Segment(clip_id=3, start=2.0, end=4.0),
                    Segment(clip_id=1, start=0.0, end=3.0),
                ],
                hook_text="Veg Momo ₹99!",
                on_screen_lines=["Garam Momos", "Special Chutney"],
                offer_text="₹99",
                price_inr=99,
                call_to_action="Visit Metro Pillar 42",
                caption="Special momos only ₹99! #momo",
                hashtags=["#momo", "#foodie", "#combo", "#offer", "#delhi"],
                language="hinglish",
            ),
        }
    )

    # Run campaign pipeline
    video = process_campaign(
        db=db,
        campaign_id=camp.id,
        provider=provider,
        llm_client=fake_llm,
        out_base_dir=str(tmp_path / "dash"),
    )
    assert video is not None

    # Check CostLog entries were persisted
    cost_entries = db.query(CostLog).filter(CostLog.campaign_id == camp.id).all()
    assert len(cost_entries) >= 3
    total_cost = sum(c.est_cost_inr for c in cost_entries)
    assert total_cost > 0.0

    # Query admin dashboard
    client = TestClient(app)
    resp = client.get(f"/admin/jobs?token={settings.ADMIN_TOKEN}")
    assert resp.status_code == 200

    html = resp.text
    # Check table contains required fields:
    # campaign id, business, state, duration, cost, error
    assert f"<td>{camp.id}</td>" in html
    assert "Tibetan Momo Corner" in html
    assert "AWAITING_APPROVAL" in html
    assert "15.0s" in html or "s</td>" in html
    assert "₹" in html
    assert "<code>-</code>" in html or "<code>" in html

