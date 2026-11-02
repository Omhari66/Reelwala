"""Tests for pipeline/render.py video composition and rendering."""

import json
from pathlib import Path

import pytest

from app.llm.schemas import Plan, Segment
from app.pipeline.ffmpeg_utils import run_ffprobe
from app.pipeline.plan import BusinessContext
from app.pipeline.render import render_video
from app.pipeline.templates import load_template
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips once for render tests."""
    temp_dir = tmp_path_factory.mktemp("fixtures")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_template_loader() -> None:
    """Test loading offer, new_dish, and behind_the_scenes templates."""
    offer_tpl = load_template("offer")
    assert offer_tpl.name == "offer"
    assert offer_tpl.target_duration_s == 15.0
    assert offer_tpl.canvas.width == 1080
    assert offer_tpl.canvas.height == 1920

    dish_tpl = load_template("new_dish")
    assert dish_tpl.name == "new_dish"
    assert dish_tpl.target_duration_s == 14.0

    bts_tpl = load_template("behind_the_scenes")
    assert bts_tpl.name == "behind_the_scenes"
    assert bts_tpl.target_duration_s == 16.0


def test_render_offer_template(fixture_clips: list[Path], tmp_path: Path) -> None:
    """Render an offer Reel from fixtures and verify dimensions, codecs, duration, and size."""
    business = BusinessContext(
        name="Tibetan Momo Corner",
        category="Food stall",
        language="hinglish",
        landmark="Near North Campus Gate",
        brand_hex="#FF5722",
    )

    # 15s plan using fixture clips
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
            Segment(clip_id=1, start=0.0, end=3.0),  # Loop back to hook moment
        ],
        hook_text="₹99 Momo Combo Alert!",
        on_screen_lines=[
            "Garam Steamed Veg Momos",
            "Spicy Red Chutney",
            "Special Limited Deal",
        ],
        offer_text="₹99 Combo",
        price_inr=99,
        call_to_action="Aaj hi aao North Campus",
        caption="College students favorite momo combo only ₹99! Visit us near North Campus Gate. #foodie",
        hashtags=["#momo", "#foodie", "#delhi", "#combo", "#offer"],
        language="hinglish",
    )

    clip_paths = {
        1: fixture_clips[0],
        2: fixture_clips[1],
        3: fixture_clips[2],
    }

    out_file = tmp_path / "rendered_offer.mp4"
    rendered_path = render_video(
        plan=plan,
        business=business,
        clip_paths=clip_paths,
        output_path=out_file,
    )

    assert rendered_path.is_file()
    size_mb = rendered_path.stat().st_size / (1024 * 1024)
    assert size_mb < 16.0

    # Probe output video
    probe_cmd = [
        "-v", "error",
        "-show_streams",
        "-show_format",
        "-print_format", "json",
        str(rendered_path),
    ]
    probe_res = run_ffprobe(probe_cmd)
    data = json.loads(probe_res.stdout)

    # Check streams
    streams = data.get("streams", [])
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

    assert video_stream is not None, "Video stream missing"
    assert audio_stream is not None, "Audio stream missing"

    assert video_stream["codec_name"] == "h264"
    assert int(video_stream["width"]) == 1080
    assert int(video_stream["height"]) == 1920
    assert audio_stream["codec_name"] == "aac"

    # Check duration
    format_info = data.get("format", {})
    duration = float(format_info.get("duration", 0.0))
    assert abs(duration - plan.target_duration_s) <= 0.5, f"Duration {duration} not within 0.5s of {plan.target_duration_s}"
