"""Tests for local metrics analysis (blur, brightness, loudness, resolution, sampling)."""

from pathlib import Path

import pytest

from app.pipeline.analyse import (
    analyse_local_metrics,
    extract_audio_loudness,
    sample_frames_at_1fps,
)
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips once for analysis tests."""
    temp_dir = tmp_path_factory.mktemp("fixtures")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_local_metrics_on_synthetic_fixtures(fixture_clips: list[Path]) -> None:
    """Test duration, fps, resolution, and blur/brightness comparison."""
    sharp_clip = fixture_clips[0]
    blurred_clip = fixture_clips[1]
    dark_clip = fixture_clips[2]

    sharp_metrics = analyse_local_metrics(sharp_clip)
    blurred_metrics = analyse_local_metrics(blurred_clip)
    dark_metrics = analyse_local_metrics(dark_clip)

    # 1. Dimensions and duration
    assert sharp_metrics.width == 1080
    assert sharp_metrics.height == 1920
    assert sharp_metrics.fps == 30.0
    assert 4.5 <= sharp_metrics.duration_s <= 5.5

    # 2. Blur comparison: Blurred clip MUST score significantly lower than sharp clip
    assert blurred_metrics.mean_blur_score < sharp_metrics.mean_blur_score
    print(f"Sharp blur: {sharp_metrics.mean_blur_score}, Blurred blur: {blurred_metrics.mean_blur_score}")

    # 3. Brightness comparison: Dark clip MUST score lower than sharp clip
    assert dark_metrics.mean_brightness < sharp_metrics.mean_brightness
    print(f"Sharp brightness: {sharp_metrics.mean_brightness}, Dark brightness: {dark_metrics.mean_brightness}")

    # 4. Audio loudness checks
    assert sharp_metrics.audio_mean_volume_db is not None
    assert sharp_metrics.audio_max_volume_db is not None
    assert sharp_metrics.audio_mean_volume_db < 0.0


def test_sample_frames_at_1fps(fixture_clips: list[Path]) -> None:
    """Verify frame sampler samples at 1fps and resizes width to 360."""
    sharp_clip = fixture_clips[0]
    frames = sample_frames_at_1fps(sharp_clip, target_width=360)

    # 5-second clip should produce ~5 sampled frames (one per second)
    assert len(frames) in (4, 5)
    for sec, frame in frames:
        h, w = frame.shape[:2]
        assert w == 360
        assert h == 640  # 1080x1920 vertical -> 360x640


def test_extract_audio_loudness_direct(fixture_clips: list[Path]) -> None:
    """Direct test for audio volume detection."""
    sharp_clip = fixture_clips[0]
    mean_vol, max_vol = extract_audio_loudness(sharp_clip)
    assert mean_vol is not None
    assert max_vol is not None
    assert mean_vol <= max_vol
