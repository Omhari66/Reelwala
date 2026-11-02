"""Tests for pipeline/quality.py covering all 10 gates, pass/fail cases, and auto-fix loop."""

from pathlib import Path

import pytest

from app.llm.schemas import ClipAnalysis, Moment, Plan, Segment
from app.pipeline.plan import BusinessContext
from app.pipeline.quality import (
    check_gate_1_duration,
    check_gate_2_format,
    check_gate_3_file_size,
    check_gate_4_first_frame,
    check_gate_5_audio,
    check_gate_6_price_match,
    check_gate_7_safe_area,
    check_gate_8_hook_timing,
    check_gate_9_forbidden_claims,
    check_gate_10_footage_sufficiency,
    run_pipeline_with_quality_autofix,
)
from app.pipeline.render import render_video
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips once for quality tests."""
    temp_dir = tmp_path_factory.mktemp("fixtures")
    return generate_synthetic_fixtures(temp_dir, force=True)


@pytest.fixture(scope="module")
def rendered_video_fixture(fixture_clips: list[Path], tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Plan, BusinessContext]:
    """Render a standard valid video once for gate testing."""
    temp_dir = tmp_path_factory.mktemp("rendered")
    biz = BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="North Gate",
        brand_hex="#FF5722",
        menu_items=[{"name": "Veg Momo", "price_inr": 99}],
    )
    plan = Plan(
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
        hook_text="₹99 Momo Combo!",
        on_screen_lines=["Garam Momos", "Special Chutney"],
        offer_text="₹99",
        price_inr=99,
        call_to_action="Aaj hi aao North Gate",
        caption="Special combo only ₹99! Visit us today.",
        hashtags=["#momo", "#foodie", "#combo", "#offer", "#delhi"],
        language="hinglish",
    )
    clip_paths = {1: fixture_clips[0], 2: fixture_clips[1], 3: fixture_clips[2]}
    out_file = temp_dir / "valid_reel.mp4"
    rendered = render_video(plan, biz, clip_paths, out_file)
    return rendered, plan, biz


def test_gate_1_duration(rendered_video_fixture: tuple[Path, Plan, BusinessContext]) -> None:
    """Test Gate 1 duration pass and fail."""
    vid, plan, _ = rendered_video_fixture
    pass_res = check_gate_1_duration(vid, target_duration_s=15.0)
    assert pass_res.passed is True

    fail_res = check_gate_1_duration(vid, target_duration_s=25.0)
    assert fail_res.passed is False


def test_gate_2_format(rendered_video_fixture: tuple[Path, Plan, BusinessContext]) -> None:
    """Test Gate 2 format: 1080x1920, h264, aac, yuv420p."""
    vid, _, _ = rendered_video_fixture
    res = check_gate_2_format(vid)
    assert res.passed is True
    assert res.value["video_codec"] == "h264"
    assert res.value["resolution"] == "1080x1920"


def test_gate_3_file_size(rendered_video_fixture: tuple[Path, Plan, BusinessContext]) -> None:
    """Test Gate 3 file size < 16MB."""
    vid, _, _ = rendered_video_fixture
    res = check_gate_3_file_size(vid)
    assert res.passed is True
    assert res.value < 16.0


def test_gate_4_first_frame(rendered_video_fixture: tuple[Path, Plan, BusinessContext], fixture_clips: list[Path]) -> None:
    """Test Gate 4 first frame sharpness and brightness."""
    vid, _, _ = rendered_video_fixture
    pass_res = check_gate_4_first_frame(vid)
    assert pass_res.passed is True

    # Dark clip first frame should fail brightness/sharpness
    fail_res = check_gate_4_first_frame(fixture_clips[2])
    assert fail_res.value["brightness"] < 35.0 or not fail_res.passed


def test_gate_5_audio(rendered_video_fixture: tuple[Path, Plan, BusinessContext]) -> None:
    """Test Gate 5 audio loudness and clipping limits."""
    vid, _, _ = rendered_video_fixture
    res = check_gate_5_audio(vid)
    assert res.passed is True
    assert res.value["mean_db"] > -50.0
    assert res.value["max_db"] < -1.0


def test_gate_6_price_match_pass_and_block_delivery() -> None:
    """Test Gate 6 price match: wrong price MUST fail and block delivery."""
    biz = BusinessContext(
        name="Tibetan Momo Corner",
        menu_items=[{"name": "Veg Momo", "price_inr": 99}],
    )

    valid_plan = Plan(
        template="offer",
        target_duration_s=15.0,
        segments=[],
        hook_text="Combo at ₹99",
        on_screen_lines=["Only ₹99"],
        offer_text="₹99",
        price_inr=99,
        call_to_action="Visit us",
        caption="Momo combo for ₹99!",
        hashtags=["#foodie", "#momo", "#offer", "#delhi", "#combo"],
        language="hinglish",
    )
    pass_res = check_gate_6_price_match(valid_plan, biz, owner_message="Momo combo")
    assert pass_res.passed is True

    # WRONG PRICE: Ad advertises ₹199 which is NOT in menu and NOT in owner message
    wrong_plan = valid_plan.model_copy(
        update={
            "hook_text": "Combo at ₹199",
            "price_inr": 199,
            "caption": "Momo combo for ₹199!",
        }
    )
    fail_res = check_gate_6_price_match(wrong_plan, biz, owner_message="Momo combo")
    assert fail_res.passed is False
    assert 199 in fail_res.value
    assert "Delivery blocked" in fail_res.message


def test_gate_7_safe_area() -> None:
    """Test Gate 7 text safe area word limits."""
    good_plan = Plan(
        template="offer",
        target_duration_s=15.0,
        segments=[],
        hook_text="Momo Combo Alert!",  # 3 words <= 6
        on_screen_lines=["Taste that stays with you"],  # 5 words <= 7
        call_to_action="Visit us today",  # 3 words <= 8
        caption="Short caption under 300 characters",
        hashtags=["#a", "#b", "#c", "#d", "#e"],
        language="hinglish",
    )
    assert check_gate_7_safe_area(good_plan).passed is True

    bad_plan = good_plan.model_copy(
        update={"hook_text": "One two three four five six seven eight"}  # 8 words > 6
    )
    assert check_gate_7_safe_area(bad_plan).passed is False


def test_gate_8_hook_timing() -> None:
    """Test Gate 8 hook timing."""
    plan = Plan(
        template="offer",
        target_duration_s=15.0,
        segments=[],
        hook_text="Hook",
        on_screen_lines=[],
        call_to_action="CTA",
        caption="Caption",
        hashtags=["#a", "#b", "#c", "#d", "#e"],
        language="hinglish",
    )
    res = check_gate_8_hook_timing(plan)
    assert res.passed is True


def test_gate_9_forbidden_claims() -> None:
    """Test Gate 9 blocks superlatives unless authorized by owner."""
    plan = Plan(
        template="offer",
        target_duration_s=15.0,
        segments=[],
        hook_text="Best in city momos!",  # Forbidden claim
        on_screen_lines=[],
        call_to_action="CTA",
        caption="Caption",
        hashtags=["#a", "#b", "#c", "#d", "#e"],
        language="hinglish",
    )
    # Fails when owner didn't say it
    fail_res = check_gate_9_forbidden_claims(plan, owner_message="Special momos")
    assert fail_res.passed is False
    assert "best in city" in fail_res.value

    # Passes when owner explicitly used it
    pass_res = check_gate_9_forbidden_claims(plan, owner_message="We are best in city")
    assert pass_res.passed is True


def test_gate_10_footage_sufficiency() -> None:
    """Test Gate 10 usable footage duration >= 6s."""
    good_clips = [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(t_start=0, t_end=4, appeal=8, sharpness=8, lighting=7, has_food=True, has_person=False, tag="food"),
                Moment(t_start=4, t_end=7, appeal=7, sharpness=6, lighting=6, has_food=True, has_person=False, tag="prep"),
            ],
            overall_note="good",
        )
    ]
    assert check_gate_10_footage_sufficiency(good_clips).passed is True

    bad_clips = [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(t_start=0, t_end=2, appeal=2, sharpness=2, lighting=3, has_food=False, has_person=False, tag="wall")
            ],
            overall_note="bad",
        )
    ]
    assert check_gate_10_footage_sufficiency(bad_clips).passed is False


def test_full_quality_report_and_autofix_loop(fixture_clips: list[Path], tmp_path: Path) -> None:
    """Test run_pipeline_with_quality_autofix automatically fixes forbidden claims."""
    biz = BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="North Gate",
        brand_hex="#FF5722",
        menu_items=[{"name": "Veg Momo", "price_inr": 99}],
    )
    plan_with_claim = Plan(
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
        hook_text="Best in city momo combo!",  # Forbidden claim to be auto-fixed
        on_screen_lines=["Garam Momos"],
        offer_text="₹99",
        price_inr=99,
        call_to_action="Aaj hi aao North Gate",
        caption="Try our momos today. #momo",
        hashtags=["#momo", "#foodie", "#offer", "#combo", "#delhi"],
        language="hinglish",
    )
    clip_paths = {1: fixture_clips[0], 2: fixture_clips[1], 3: fixture_clips[2]}
    clip_analyses = [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(t_start=0, t_end=5, appeal=8, sharpness=8, lighting=7, has_food=True, has_person=False, tag="food"),
                Moment(t_start=0, t_end=5, appeal=7, sharpness=7, lighting=7, has_food=True, has_person=False, tag="food2"),
            ],
            overall_note="clean",
        )
    ]

    out_file = tmp_path / "autofix_reel.mp4"
    rendered, report = run_pipeline_with_quality_autofix(
        plan=plan_with_claim,
        business=biz,
        clip_paths=clip_paths,
        clip_analyses=clip_analyses,
        output_path=out_file,
        owner_message="Special momos ₹99",
    )

    assert rendered.is_file()
    assert "Removed forbidden claims" in report.auto_fix_actions
    assert report.passed_all is True
