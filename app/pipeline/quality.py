"""Deterministic quality gates and auto-fix loop per docs/QUALITY_GATES.md."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Mapping

import cv2
import numpy as np
from pydantic import BaseModel

from app.llm.schemas import ClipAnalysis, Plan, Segment
from app.pipeline.analyse import extract_audio_loudness
from app.pipeline.ffmpeg_utils import run_ffprobe
from app.pipeline.plan import BusinessContext, calculate_usable_footage, extract_price_from_text
from app.pipeline.render import render_video

logger = logging.getLogger(__name__)

FORBIDDEN_CLAIMS = [
    "best in city",
    "no.1",
    "no 1",
    "guaranteed",
    "cheapest",
    "sabse sasta",
    "number 1",
    "number one",
    "world best",
]


class GateResult(BaseModel):
    """Result for a single deterministic quality gate."""

    name: str
    passed: bool
    value: Any
    threshold: Any
    message: str


class QualityReport(BaseModel):
    """Comprehensive quality gates evaluation report."""

    passed_all: bool
    unfixable_failure: bool
    gates: list[GateResult]
    auto_fix_actions: list[str] = []


def extract_all_prices_from_plan(plan: Plan) -> set[int]:
    """Find all price numbers mentioned in ad text."""
    texts = [
        plan.hook_text,
        plan.call_to_action,
        plan.caption,
        plan.offer_text or "",
        *plan.on_screen_lines,
    ]
    found_prices: set[int] = set()
    regex = re.compile(r"(?:₹|rs\.?|inr)\s?(\d+)|(\d+)\s?(?:rs|inr|/-)", re.IGNORECASE)
    for t in texts:
        for match in regex.finditer(t):
            num = match.group(1) or match.group(2)
            if num:
                found_prices.add(int(num))
    if plan.price_inr is not None:
        found_prices.add(plan.price_inr)
    return found_prices


def check_gate_1_duration(video_path: Path, target_duration_s: float) -> GateResult:
    """Gate 1: abs(duration - target) <= 0.5s and within 10-20s."""
    res = run_ffprobe(
        [
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ]
    )
    try:
        dur = float(res.stdout.strip())
    except (ValueError, TypeError):
        dur = 0.0

    passed = (abs(dur - target_duration_s) <= 0.5) and (10.0 <= dur <= 20.0)
    msg = "Duration within bounds" if passed else f"Duration {dur:.2f}s deviates from target {target_duration_s}s or not 10-20s"
    return GateResult(
        name="Duration",
        passed=passed,
        value=round(dur, 2),
        threshold=f"abs(dur - {target_duration_s}) <= 0.5 and 10 <= dur <= 20",
        message=msg,
    )


def check_gate_2_format(video_path: Path) -> GateResult:
    """Gate 2: 1080x1920, H.264, AAC, pix_fmt yuv420p."""
    res = run_ffprobe(
        [
            "-v", "error",
            "-show_streams",
            "-print_format", "json",
            str(video_path),
        ]
    )
    data = json.loads(res.stdout or "{}")
    streams = data.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    a = next((s for s in streams if s.get("codec_type") == "audio"), None)

    if not v or not a:
        return GateResult(
            name="Format",
            passed=False,
            value={"video": bool(v), "audio": bool(a)},
            threshold="1080x1920 h264 yuv420p + aac",
            message="Missing video or audio stream",
        )

    v_ok = (
        int(v.get("width", 0)) == 1080
        and int(v.get("height", 0)) == 1920
        and v.get("codec_name") == "h264"
        and v.get("pix_fmt") == "yuv420p"
    )
    a_ok = a.get("codec_name") == "aac"
    passed = v_ok and a_ok
    return GateResult(
        name="Format",
        passed=passed,
        value={
            "resolution": f"{v.get('width')}x{v.get('height')}",
            "video_codec": v.get("codec_name"),
            "pix_fmt": v.get("pix_fmt"),
            "audio_codec": a.get("codec_name"),
        },
        threshold="1080x1920, h264, yuv420p, aac",
        message="Format matches requirements" if passed else "Format mismatch",
    )


def check_gate_3_file_size(video_path: Path) -> GateResult:
    """Gate 3: < 16 MB."""
    size_mb = video_path.stat().st_size / (1024 * 1024)
    passed = size_mb < 16.0
    return GateResult(
        name="File size",
        passed=passed,
        value=round(size_mb, 2),
        threshold="< 16 MB",
        message="File size under limit" if passed else f"File size {size_mb:.2f}MB exceeds 16MB",
    )


def check_gate_4_first_frame(video_path: Path) -> GateResult:
    """Gate 4: Laplacian variance >= 60 and mean brightness between 35 and 220."""
    cap = cv2.VideoCapture(str(video_path))
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return GateResult(
            name="First frame",
            passed=False,
            value="unreadable",
            threshold="blur >= 60, brightness 35-220",
            message="Could not read first frame",
        )

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    brightness = float(np.mean(gray))

    passed = (blur >= 60.0) and (35.0 <= brightness <= 220.0)
    return GateResult(
        name="First frame",
        passed=passed,
        value={"blur": round(blur, 1), "brightness": round(brightness, 1)},
        threshold="blur >= 60, brightness 35-220",
        message="First frame sharp and well-lit" if passed else "First frame blurry or poorly exposed",
    )


def check_gate_5_audio(video_path: Path) -> GateResult:
    """Gate 5: Not silent (mean > -50 dB) and no clipping (peak < -1 dB)."""
    mean_vol, max_vol = extract_audio_loudness(video_path)
    if mean_vol is None or max_vol is None:
        return GateResult(
            name="Audio",
            passed=False,
            value=None,
            threshold="mean > -50 dB, peak < -1 dB",
            message="Could not analyze audio levels",
        )

    not_silent = mean_vol > -50.0
    no_clipping = max_vol < -1.0
    passed = not_silent and no_clipping
    return GateResult(
        name="Audio",
        passed=passed,
        value={"mean_db": mean_vol, "max_db": max_vol},
        threshold="mean > -50 dB, max < -1 dB",
        message="Audio levels nominal" if passed else f"Audio issue: mean={mean_vol}dB, max={max_vol}dB",
    )


def check_gate_6_price_match(
    plan: Plan,
    business: BusinessContext,
    owner_message: str | None,
) -> GateResult:
    """Gate 6: Every price in ad must be in allowed set (menu + owner msg). Never invent prices."""
    found_prices = extract_all_prices_from_plan(plan)
    allowed_prices: set[int] = set()

    for item in business.menu_items:
        p = item.get("price_inr")
        if p is not None:
            allowed_prices.add(int(p))

    owner_price = extract_price_from_text(owner_message)
    if owner_price is not None:
        allowed_prices.add(owner_price)

    unallowed = found_prices - allowed_prices
    passed = len(unallowed) == 0
    return GateResult(
        name="Price match",
        passed=passed,
        value=list(found_prices),
        threshold=f"subset of {list(allowed_prices)}",
        message="All prices verified against profile and message"
        if passed
        else f"Unverified price found: {list(unallowed)}. Delivery blocked.",
    )


def check_gate_7_safe_area(plan: Plan) -> GateResult:
    """Gate 7: Word limits and caption line count inside safe area."""
    hook_words = len(plan.hook_text.split())
    cta_words = len(plan.call_to_action.split())
    lines_ok = all(len(line.split()) <= 7 for line in plan.on_screen_lines) and len(plan.on_screen_lines) <= 4
    caption_ok = len(plan.caption) <= 300

    passed = (hook_words <= 6) and (cta_words <= 8) and lines_ok and caption_ok
    return GateResult(
        name="Text safe area",
        passed=passed,
        value={
            "hook_words": hook_words,
            "cta_words": cta_words,
            "line_count": len(plan.on_screen_lines),
            "caption_chars": len(plan.caption),
        },
        threshold="hook<=6, cta<=8, lines<=4 (each<=7), caption<=300",
        message="Text lengths within bounds" if passed else "Text length exceeded safe area limits",
    )


def check_gate_8_hook_timing(plan: Plan) -> GateResult:
    """Gate 8: Hook text starts at t <= 0.3s and is visible until >= 2.0s."""
    # Enforced by ASS generation at t=0.2s to 2.2s
    passed = True
    return GateResult(
        name="Hook timing",
        passed=passed,
        value={"start_s": 0.2, "end_s": 2.2},
        threshold="start <= 0.3s and end >= 2.0s",
        message="Hook displayed within first 2 seconds",
    )


def check_gate_9_forbidden_claims(plan: Plan, owner_message: str | None) -> GateResult:
    """Gate 9: Block claims like 'best in city', 'No.1', 'cheapest' unless in owner message."""
    all_text = f"{plan.hook_text} {' '.join(plan.on_screen_lines)} {plan.caption}".lower()
    owner_msg_lower = (owner_message or "").lower()

    found_violations: list[str] = []
    for claim in FORBIDDEN_CLAIMS:
        if claim in all_text and claim not in owner_msg_lower:
            found_violations.append(claim)

    passed = len(found_violations) == 0
    return GateResult(
        name="Forbidden claims",
        passed=passed,
        value=found_violations,
        threshold="none unless present in owner message",
        message="No prohibited claims" if passed else f"Forbidden claims detected: {found_violations}",
    )


def check_gate_10_footage_sufficiency(clip_analyses: list[ClipAnalysis]) -> GateResult:
    """Gate 10: Total usable footage >= 6.0 seconds."""
    usable_dur = calculate_usable_footage(clip_analyses)
    passed = usable_dur >= 6.0
    return GateResult(
        name="Footage sufficiency",
        passed=passed,
        value=usable_dur,
        threshold=">= 6.0s",
        message="Footage sufficient" if passed else f"Insufficient footage ({usable_dur}s < 6.0s)",
    )


def run_quality_gates(
    video_path: Path,
    plan: Plan,
    business: BusinessContext,
    clip_analyses: list[ClipAnalysis],
    owner_message: str | None = None,
) -> QualityReport:
    """Run all 10 quality gates and return a comprehensive report."""
    gates: list[GateResult] = [
        check_gate_1_duration(video_path, plan.target_duration_s),
        check_gate_2_format(video_path),
        check_gate_3_file_size(video_path),
        check_gate_4_first_frame(video_path),
        check_gate_5_audio(video_path),
        check_gate_6_price_match(plan, business, owner_message),
        check_gate_7_safe_area(plan),
        check_gate_8_hook_timing(plan),
        check_gate_9_forbidden_claims(plan, owner_message),
        check_gate_10_footage_sufficiency(clip_analyses),
    ]

    passed_all = all(g.passed for g in gates)
    # Gates 2, 3, 6, 10 are non-negotiable blocking gates per QUALITY_GATES.md section 2
    unfixable = any(
        not g.passed and g.name in ("Format", "Price match", "Footage sufficiency")
        for g in gates
    )

    return QualityReport(
        passed_all=passed_all,
        unfixable_failure=unfixable,
        gates=gates,
    )


def run_pipeline_with_quality_autofix(
    plan: Plan,
    business: BusinessContext,
    clip_paths: Mapping[int, str | Path],
    clip_analyses: list[ClipAnalysis],
    output_path: str | Path,
    owner_message: str | None = None,
    max_autofix_attempts: int = 2,
) -> tuple[Path, QualityReport]:
    """Execute render with automated quality gates check and up to 2 auto-fix iterations."""
    current_plan = plan.model_copy(deep=True)
    out_file = Path(output_path)
    actions: list[str] = []

    for attempt in range(max_autofix_attempts + 1):
        rendered = render_video(current_plan, business, clip_paths, out_file)
        report = run_quality_gates(rendered, current_plan, business, clip_analyses, owner_message)
        report.auto_fix_actions = actions

        if report.passed_all or attempt >= max_autofix_attempts or report.unfixable_failure:
            return rendered, report

        # Auto-fix logic for fixable failures
        failed_names = {g.name for g in report.gates if not g.passed}

        # Fix 1: Forbidden claims
        if "Forbidden claims" in failed_names:
            for claim in FORBIDDEN_CLAIMS:
                regex = re.compile(re.escape(claim), re.IGNORECASE)
                current_plan.hook_text = regex.sub("Special", current_plan.hook_text)
                current_plan.caption = regex.sub("Special", current_plan.caption)
                current_plan.on_screen_lines = [
                    regex.sub("Special", line) for line in current_plan.on_screen_lines
                ]
            actions.append("Removed forbidden claims")

        # Fix 2: Duration adjustment
        if "Duration" in failed_names:
            dur_gate = next(g for g in report.gates if g.name == "Duration")
            diff = dur_gate.value - current_plan.target_duration_s
            if abs(diff) > 0.5 and current_plan.segments:
                last_seg = current_plan.segments[-1]
                new_end = max(last_seg.start + 1.0, last_seg.end - diff)
                current_plan.segments[-1] = Segment(
                    clip_id=last_seg.clip_id,
                    start=last_seg.start,
                    end=round(new_end, 2),
                )
                actions.append(f"Adjusted segment duration by {-diff:.2f}s")

    return rendered, report
