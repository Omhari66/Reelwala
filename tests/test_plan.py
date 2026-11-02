"""Unit tests for pipeline/plan.py covering valid plan, retry, insufficient footage, and fallback."""

from app.llm.client import FakeLLMClient
from app.llm.schemas import ClipAnalysis, InsufficientFootage, Moment, Plan
from app.pipeline.plan import (
    BusinessContext,
    build_deterministic_fallback_plan,
    calculate_usable_footage,
    plan_ad_campaign,
)


def sample_business() -> BusinessContext:
    """Return a sample BusinessContext."""
    return BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="North Campus Gate 4",
        brand_hex="#FF5722",
        menu_items=[{"name": "Steamed Veg Momo", "price_inr": 60}],
    )


def sample_usable_clips() -> list[ClipAnalysis]:
    """Return clip analyses with sufficient usable footage (>= 6s total)."""
    return [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(
                    t_start=0.0,
                    t_end=3.0,
                    appeal=8,
                    sharpness=8,
                    lighting=7,
                    has_food=True,
                    has_person=False,
                    tag="steam momo close-up",
                ),
                Moment(
                    t_start=3.0,
                    t_end=5.0,
                    appeal=7,
                    sharpness=7,
                    lighting=7,
                    has_food=True,
                    has_person=False,
                    tag="chutney dip",
                ),
            ],
            overall_note="sharp and appetising",
        ),
        ClipAnalysis(
            clip_id=2,
            moments=[
                Moment(
                    t_start=0.0,
                    t_end=4.0,
                    appeal=7,
                    sharpness=6,
                    lighting=6,
                    has_food=True,
                    has_person=True,
                    tag="owner plating",
                )
            ],
            overall_note="clean shot",
        ),
    ]


def sample_low_quality_clips() -> list[ClipAnalysis]:
    """Return clip analyses with under 6 seconds of usable footage."""
    return [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(
                    t_start=0.0,
                    t_end=3.0,
                    appeal=3,
                    sharpness=2,
                    lighting=3,
                    has_food=False,
                    has_person=False,
                    tag="blurry wall",
                )
            ],
            overall_note="dark and blurry",
        )
    ]


def test_calculate_usable_footage() -> None:
    """Test calculation of usable footage duration."""
    clips = sample_usable_clips()
    usable = calculate_usable_footage(clips)
    # Clip 1 has 3.0s + 2.0s = 5.0s, Clip 2 has 4.0s = 9.0s total
    assert usable == 9.0

    low_clips = sample_low_quality_clips()
    assert calculate_usable_footage(low_clips) == 0.0


def test_plan_valid() -> None:
    """Test plan generation when LLM returns a valid Plan."""
    canned_plan = Plan(
        template="offer",
        target_duration_s=15.0,
        segments=[
            {"clip_id": 1, "start": 0.0, "end": 2.0},
            {"clip_id": 2, "start": 0.0, "end": 2.0},
            {"clip_id": 1, "start": 0.0, "end": 2.0},
        ],
        hook_text="₹99 momo combo!",
        on_screen_lines=["Garam veg momos", "Special chutney"],
        offer_text="₹99",
        price_inr=99,
        call_to_action="Aaj hi aao North Campus Gate 4",
        caption="Try our best combo at Tibetan Momo Corner!",
        hashtags=["#momo", "#foodie", "#delhi", "#combo", "#offer"],
        language="hinglish",
    )
    fake_llm = FakeLLMClient(canned_responses=[canned_plan])
    result = plan_ad_campaign(
        business=sample_business(),
        owner_message="Momo combo ₹99",
        clip_analyses=sample_usable_clips(),
        llm_client=fake_llm,
    )

    assert isinstance(result, Plan)
    assert result.template == "offer"
    assert result.price_inr == 99
    assert len(fake_llm.call_history) == 1


def test_plan_invalid_triggers_retry_then_succeeds() -> None:
    """Test that invalid output on attempt 1 triggers retry with error context."""
    valid_plan = Plan(
        template="new_dish",
        target_duration_s=14.0,
        segments=[{"clip_id": 1, "start": 0.0, "end": 2.0}],
        hook_text="Naya dish try karo!",
        on_screen_lines=["Fresh flavours", "Special recipe"],
        call_to_action="Aaj hi visit karein",
        caption="New momo variety launched!",
        hashtags=["#new", "#momo", "#taste", "#delhi", "#food"],
        language="hinglish",
    )
    fake_llm = FakeLLMClient(
        canned_responses=[
            {"bad_json": True},  # Fails attempt 1
            valid_plan,          # Succeeds on retry
        ]
    )
    result = plan_ad_campaign(
        business=sample_business(),
        owner_message="Naya dish",
        clip_analyses=sample_usable_clips(),
        llm_client=fake_llm,
    )

    assert isinstance(result, Plan)
    assert result.template == "new_dish"
    assert len(fake_llm.call_history) == 2
    assert "Previous attempt failed" in fake_llm.call_history[1]["prompt"]


def test_plan_insufficient_footage_detection() -> None:
    """Test that poor footage triggers InsufficientFootage with specific filming tip."""
    fake_llm = FakeLLMClient(canned_responses=[])
    result = plan_ad_campaign(
        business=sample_business(),
        owner_message="promote this",
        clip_analyses=sample_low_quality_clips(),
        llm_client=fake_llm,
    )

    assert isinstance(result, InsufficientFootage)
    assert result.insufficient_footage is True
    assert "film karein" in result.tip


def test_plan_fallback_on_double_failure() -> None:
    """Test that repeated LLM failure returns deterministic fallback plan."""
    fake_llm = FakeLLMClient(
        canned_responses=[
            {"corrupt": 1},
            {"corrupt": 2},
        ]
    )
    result = plan_ad_campaign(
        business=sample_business(),
        owner_message="Special combo ₹99",
        clip_analyses=sample_usable_clips(),
        llm_client=fake_llm,
    )

    assert isinstance(result, Plan)
    assert result.template == "offer"
    assert result.price_inr == 99
    assert len(result.segments) >= 2
    # Ending segment visually loops back to hook moment
    assert result.segments[-1].clip_id == result.segments[0].clip_id


def test_build_deterministic_fallback_plan_direct() -> None:
    """Direct test for deterministic fallback plan generator."""
    biz = sample_business()
    clips = sample_usable_clips()
    plan = build_deterministic_fallback_plan(
        business=biz,
        owner_message="New dish momo",
        clip_analyses=clips,
    )
    assert isinstance(plan, Plan)
    assert plan.template == "new_dish"
    assert "Tibetan Momo Corner" in plan.caption
