"""Tests for vision LLM analysis, retry handling, safe fallback, and parallel execution."""

import re
from pathlib import Path

import pytest

from app.llm.client import FakeLLMClient
from app.llm.schemas import ClipAnalysis, Moment
from app.pipeline.analyse import (
    analyse_clip_vision,
    analyse_clips_parallel,
)
from tests.make_fixtures import generate_synthetic_fixtures


@pytest.fixture(scope="module")
def fixture_clips(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    """Generate synthetic clips once for vision tests."""
    temp_dir = tmp_path_factory.mktemp("fixtures")
    return generate_synthetic_fixtures(temp_dir, force=True)


def test_analyse_clip_vision_success(fixture_clips: list[Path]) -> None:
    """Test successful vision analysis with FakeLLMClient."""
    valid_analysis = ClipAnalysis(
        clip_id=1,
        moments=[
            Moment(
                t_start=0.0,
                t_end=2.0,
                appeal=8,
                sharpness=8,
                lighting=7,
                has_food=True,
                has_person=False,
                tag="steam close-up",
            ),
            Moment(
                t_start=2.0,
                t_end=5.0,
                appeal=7,
                sharpness=7,
                lighting=7,
                has_food=True,
                has_person=True,
                tag="owner serving",
            ),
        ],
        overall_note="great steam and lighting",
    )
    fake_llm = FakeLLMClient(canned_responses=[valid_analysis])
    result = analyse_clip_vision(clip_id=1, video_path=fixture_clips[0], llm_client=fake_llm)

    assert result.clip_id == 1
    assert len(result.moments) == 2
    assert result.moments[0].appeal == 8
    assert len(fake_llm.call_history) == 1


def test_analyse_clip_vision_retry_then_success(fixture_clips: list[Path]) -> None:
    """Test that invalid first response triggers retry, which then succeeds."""
    valid_analysis = ClipAnalysis(
        clip_id=1,
        moments=[
            Moment(
                t_start=0.0,
                t_end=4.0,
                appeal=6,
                sharpness=6,
                lighting=6,
                has_food=True,
                has_person=False,
                tag="cooking action",
            )
        ],
        overall_note="good action",
    )
    # 1st call returns invalid dict (missing required moments field) -> triggers retry; 2nd succeeds
    fake_llm = FakeLLMClient(
        canned_responses=[
            {"clip_id": 1, "invalid_field": True},
            valid_analysis,
        ]
    )
    result = analyse_clip_vision(clip_id=1, video_path=fixture_clips[0], llm_client=fake_llm)

    assert result.clip_id == 1
    assert len(result.moments) == 1
    assert result.moments[0].appeal == 6
    assert len(fake_llm.call_history) == 2
    assert "Previous attempt failed" in fake_llm.call_history[1]["prompt"]


def test_analyse_clip_vision_fallback_on_double_failure(fixture_clips: list[Path]) -> None:
    """Test that two failures trigger the safe fallback where all moments are scored 5."""
    fake_llm = FakeLLMClient(
        canned_responses=[
            {"invalid": 1},
            {"invalid": 2},
        ]
    )
    result = analyse_clip_vision(clip_id=1, video_path=fixture_clips[0], llm_client=fake_llm)

    assert result.clip_id == 1
    assert "safe fallback" in result.overall_note
    assert len(result.moments) >= 2
    for m in result.moments:
        assert m.appeal == 5
        assert m.sharpness == 5
        assert m.lighting == 5


def test_analyse_clips_parallel(fixture_clips: list[Path]) -> None:
    """Test running vision analysis across multiple clips in parallel."""
    def make_analysis(cid: int) -> ClipAnalysis:
        return ClipAnalysis(
            clip_id=cid,
            moments=[
                Moment(
                    t_start=0.0,
                    t_end=3.0,
                    appeal=7,
                    sharpness=7,
                    lighting=7,
                    has_food=True,
                    has_person=False,
                    tag=f"clip {cid} food",
                )
            ],
            overall_note=f"clip {cid} note",
        )

    def canned_handler(prompt: str, schema: type) -> ClipAnalysis:
        match = re.search(r"Clip ID: (\d+)", prompt)
        cid = int(match.group(1)) if match else 1
        return make_analysis(cid)

    fake_llm = FakeLLMClient(canned_responses=canned_handler)


    clip_items = [
        (1, fixture_clips[0]),
        (2, fixture_clips[1]),
        (3, fixture_clips[2]),
    ]
    results = analyse_clips_parallel(clip_items, llm_client=fake_llm, max_workers=3)

    assert len(results) == 3
    assert [r.clip_id for r in results] == [1, 2, 3]
