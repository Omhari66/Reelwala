"""Tests for scripts/run_local.py CLI execution."""

from pathlib import Path

import pytest

from scripts.run_local import run_pipeline
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips once for CLI tests."""
    temp_dir = tmp_path_factory.mktemp("fixtures")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_run_pipeline_cli_end_to_end(fixture_clips: list[Path], tmp_path: Path) -> None:
    """Test full pipeline execution producing preview.mp4, plan.json, quality_report.json, and cost.json."""
    clip_paths = [str(c) for c in fixture_clips]
    res = run_pipeline(
        clip_paths=clip_paths,
        message="Special momo combo Rs 99 for students",
        business_source=None,
        out_dir=str(tmp_path),
        use_fake_llm=True,
    )

    assert "preview_path" in res
    assert Path(res["preview_path"]).is_file()
    assert (tmp_path / "preview.mp4").is_file()
    assert (tmp_path / "plan.json").is_file()
    assert (tmp_path / "quality_report.json").is_file()
    assert (tmp_path / "cost.json").is_file()

    assert res["quality_report"]["passed_all"] is True
    assert res["timings"]["total_duration_s"] > 0.0
