"""Tests for synthetic fixtures generator."""

from pathlib import Path

from tests.make_fixtures import generate_synthetic_fixtures


def test_generate_synthetic_fixtures(tmp_path: Path) -> None:
    """Verify that generate_synthetic_fixtures creates 3 valid vertical MP4 clips."""
    clips = generate_synthetic_fixtures(tmp_path, force=True)
    assert len(clips) == 3
    for clip in clips:
        assert clip.is_file()
        assert clip.stat().st_size > 1000
        assert clip.suffix == ".mp4"
