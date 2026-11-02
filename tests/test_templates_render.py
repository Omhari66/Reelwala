"""Tests for rendering new_dish and behind_the_scenes templates and passing quality gates."""

from pathlib import Path

import pytest

from app.llm.schemas import ClipAnalysis, Moment, Plan, Segment
from app.pipeline.plan import BusinessContext
from app.pipeline.quality import run_quality_gates
from app.pipeline.render import render_video
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips once for template render tests."""
    temp_dir = tmp_path_factory.mktemp("fixtures")
    return generate_synthetic_fixtures(temp_dir, force=True)


@pytest.fixture(scope="module")
def sample_business() -> BusinessContext:
    """Return a standard business context."""
    return BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="North Campus Gate",
        brand_hex="#FF5722",
        menu_items=[
            {"name": "Steamed Veg Momo", "price_inr": 60},
            {"name": "Fried Chicken Momo", "price_inr": 90},
            {"name": "Special Kurkure Momo", "price_inr": 110},
        ],
    )


@pytest.fixture(scope="module")
def sample_clip_analyses() -> list[ClipAnalysis]:
    """Return clip analyses with sufficient usable footage."""
    return [
        ClipAnalysis(
            clip_id=1,
            moments=[
                Moment(t_start=0, t_end=5, appeal=8, sharpness=8, lighting=7, has_food=True, has_person=False, tag="hot momo"),
                Moment(t_start=0, t_end=5, appeal=7, sharpness=7, lighting=7, has_food=True, has_person=False, tag="steamer"),
            ],
            overall_note="sharp and appetising",
        )
    ]


def test_render_new_dish_template(
    fixture_clips: list[Path],
    sample_business: BusinessContext,
    sample_clip_analyses: list[ClipAnalysis],
    tmp_path: Path,
) -> None:
    """Render a new_dish Reel (target 14s) and assert all quality gates pass."""
    plan = Plan(
        template="new_dish",
        target_duration_s=14.0,
        segments=[
            Segment(clip_id=1, start=0.0, end=2.0),
            Segment(clip_id=2, start=0.0, end=3.0),
            Segment(clip_id=3, start=0.0, end=3.0),
            Segment(clip_id=1, start=2.0, end=4.0),
            Segment(clip_id=2, start=2.0, end=4.0),
            Segment(clip_id=1, start=0.0, end=2.0),  # Loop
        ],
        hook_text="Naya Kurkure Momo Launch!",
        on_screen_lines=["Special Kurkure Momo", "Super Crispy Crunch"],
        offer_text=None,
        price_inr=110,
        call_to_action="Aaj hi aao North Campus",
        caption="Try our newly launched Special Kurkure Momo for ₹110! Crispy and spicy. #momo",
        hashtags=["#newdish", "#kurkuremomo", "#delhifood", "#taste", "#momo"],
        language="hinglish",
    )
    clip_paths = {1: fixture_clips[0], 2: fixture_clips[1], 3: fixture_clips[2]}
    out_video = tmp_path / "new_dish_preview.mp4"

    rendered = render_video(plan, sample_business, clip_paths, out_video)
    assert rendered.is_file()

    report = run_quality_gates(rendered, plan, sample_business, sample_clip_analyses, owner_message="Naya Kurkure Momo ₹110")
    assert report.passed_all is True, f"Failed gates: {[g.name for g in report.gates if not g.passed]}"


def test_render_behind_the_scenes_template(
    fixture_clips: list[Path],
    sample_business: BusinessContext,
    sample_clip_analyses: list[ClipAnalysis],
    tmp_path: Path,
) -> None:
    """Render a behind_the_scenes Reel (target 16s) and assert all quality gates pass."""
    plan = Plan(
        template="behind_the_scenes",
        target_duration_s=16.0,
        segments=[
            Segment(clip_id=1, start=0.0, end=2.0),
            Segment(clip_id=2, start=0.0, end=2.5),
            Segment(clip_id=3, start=0.0, end=2.5),
            Segment(clip_id=1, start=2.0, end=4.5),
            Segment(clip_id=2, start=2.0, end=4.5),
            Segment(clip_id=3, start=2.5, end=4.5),
            Segment(clip_id=1, start=0.0, end=2.0),  # Loop
        ],

        hook_text="Dekho kaise bante hain!",
        on_screen_lines=["Roz subah fresh preparation", "Pure ingredients"],
        offer_text=None,
        price_inr=None,
        call_to_action="Aaj hi aao North Campus",
        caption="Peeche ka sach! Roz subah fresh momos bante hain at Tibetan Momo Corner. #foodie",
        hashtags=["#behindthescenes", "#makingof", "#streetfood", "#delhifood", "#momo"],
        language="hinglish",
    )
    clip_paths = {1: fixture_clips[0], 2: fixture_clips[1], 3: fixture_clips[2]}
    out_video = tmp_path / "bts_preview.mp4"

    rendered = render_video(plan, sample_business, clip_paths, out_video)
    assert rendered.is_file()

    report = run_quality_gates(rendered, plan, sample_business, sample_clip_analyses, owner_message="Hamari fresh preparation")
    assert report.passed_all is True, f"Failed gates: {[g.name for g in report.gates if not g.passed]}"
