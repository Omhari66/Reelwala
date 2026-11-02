"""Tests for pipeline/revise.py covering price update, shorter, hook regeneration, approval, and limit enforcement."""

import pytest

from app.llm.client import FakeLLMClient
from app.llm.schemas import ClipAnalysis, Moment, Plan, RevisionRequest, Segment
from app.pipeline.plan import BusinessContext
from app.pipeline.revise import apply_revision, parse_revision_request


@pytest.fixture
def sample_business() -> BusinessContext:
    """Return sample business context."""
    return BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="North Gate",
        brand_hex="#FF5722",
        menu_items=[
            {"name": "Veg Momo", "price_inr": 99},
            {"name": "Combo Momo", "price_inr": 129},
        ],
    )


@pytest.fixture
def base_plan() -> Plan:
    """Return base Plan before revisions."""
    return Plan(
        template="offer",
        target_duration_s=16.0,
        segments=[
            Segment(clip_id=1, start=0.0, end=2.0),
            Segment(clip_id=2, start=0.0, end=4.0),
            Segment(clip_id=3, start=0.0, end=4.0),
            Segment(clip_id=1, start=2.0, end=4.0),
            Segment(clip_id=1, start=0.0, end=2.0),
        ],
        hook_text="₹99 Momo Combo!",
        on_screen_lines=["Garam Momos at ₹99", "Special Chutney"],
        offer_text="₹99",
        price_inr=99,
        call_to_action="Aaj hi aao North Gate",
        caption="Try our special combo for ₹99! #momo",
        hashtags=["#momo", "#foodie", "#delhi"],
        language="hinglish",
    )


@pytest.fixture
def sample_clips() -> list[ClipAnalysis]:
    """Return sample clip analyses."""
    return [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(t_start=0, t_end=4, appeal=8, sharpness=8, lighting=7, has_food=True, has_person=False, tag="food")
            ],
            overall_note="good",
        )
    ]


def test_parse_and_apply_price_revision(base_plan: Plan, sample_business: BusinessContext, sample_clips: list[ClipAnalysis]) -> None:
    """Test 'price 129' updates price across all fields."""
    fake_llm = FakeLLMClient(canned_responses=[RevisionRequest(price_inr=129)])
    req = parse_revision_request("price 129", base_plan, sample_business, fake_llm)
    assert req.price_inr == 129

    new_plan, status = apply_revision(base_plan, req, revision_count=0, business=sample_business, clip_analyses=sample_clips)
    assert status == "revised"
    assert new_plan.price_inr == 129
    assert new_plan.offer_text == "₹129"
    assert "₹129" in new_plan.hook_text
    assert "₹129" in new_plan.caption
    assert any("₹129" in line for line in new_plan.on_screen_lines)


def test_parse_and_apply_shorter(base_plan: Plan, sample_business: BusinessContext, sample_clips: list[ClipAnalysis]) -> None:
    """Test 'shorter' reduces target duration by ~25%."""
    fake_llm = FakeLLMClient(canned_responses=[RevisionRequest(shorter=True)])
    req = parse_revision_request("shorter", base_plan, sample_business, fake_llm)
    assert req.shorter is True

    new_plan, status = apply_revision(base_plan, req, revision_count=1, business=sample_business, clip_analyses=sample_clips)
    assert status == "revised"
    # 16.0s reduced by 25% = 12.0s
    assert new_plan.target_duration_s == 12.0
    total_seg_len = sum(s.end - s.start for s in new_plan.segments)
    assert total_seg_len < sum(s.end - s.start for s in base_plan.segments)


def test_parse_and_apply_naya_hook(base_plan: Plan, sample_business: BusinessContext, sample_clips: list[ClipAnalysis]) -> None:
    """Test 'naya hook' regenerates the hook text."""
    fake_llm = FakeLLMClient(canned_responses=[RevisionRequest(regenerate_hook=True)])
    req = parse_revision_request("naya hook", base_plan, sample_business, fake_llm)
    assert req.regenerate_hook is True

    new_plan, status = apply_revision(base_plan, req, revision_count=1, business=sample_business, clip_analyses=sample_clips)
    assert status == "revised"
    assert new_plan.hook_text != base_plan.hook_text


def test_parse_and_apply_approval(base_plan: Plan, sample_business: BusinessContext, sample_clips: list[ClipAnalysis]) -> None:
    """Test 'ok' resolves to approve status."""
    fake_llm = FakeLLMClient(canned_responses=[])
    req = parse_revision_request("ok", base_plan, sample_business, fake_llm)
    assert req.approve is True

    _, status = apply_revision(base_plan, req, revision_count=2, business=sample_business, clip_analyses=sample_clips)
    assert status == "approved"


def test_parse_gibberish_returns_unclear(base_plan: Plan, sample_business: BusinessContext, sample_clips: list[ClipAnalysis]) -> None:
    """Test that gibberish or unrelated message resolves to unclear."""
    fake_llm = FakeLLMClient(canned_responses=[RevisionRequest(unclear=True)])
    req = parse_revision_request("asdfqwerty 1234 xyz", base_plan, sample_business, fake_llm)
    assert req.unclear is True

    _, status = apply_revision(base_plan, req, revision_count=1, business=sample_business, clip_analyses=sample_clips)
    assert status == "unclear"


def test_revision_limit_enforced(base_plan: Plan, sample_business: BusinessContext, sample_clips: list[ClipAnalysis]) -> None:
    """Test that more than 3 revisions raises ValueError."""
    req = RevisionRequest(shorter=True)
    with pytest.raises(ValueError, match="Maximum revision limit reached"):
        apply_revision(base_plan, req, revision_count=3, business=sample_business, clip_analyses=sample_clips)
