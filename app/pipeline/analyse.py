"""Deterministic OpenCV and FFmpeg local metrics, frame sampling, and vision LLM analysis."""

import base64
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np
from pydantic import BaseModel, ValidationError

from app.llm.client import LLMClient
from app.llm.schemas import ClipAnalysis, Moment
from app.pipeline.ffmpeg_utils import run_ffmpeg

logger = logging.getLogger(__name__)

PROMPT_PATH = Path(__file__).resolve().parents[1] / "llm" / "prompts" / "analyse_v1.md"


class SecondMetric(BaseModel):
    """Metrics for a single second of video."""

    second: int
    blur_score: float  # Laplacian variance
    brightness: float  # Grayscale mean (0-255)


class LocalClipMetrics(BaseModel):
    """Complete local metrics for a clip."""

    duration_s: float
    fps: float
    width: int
    height: int
    per_second_metrics: list[SecondMetric]
    mean_blur_score: float
    mean_brightness: float
    audio_mean_volume_db: float | None = None
    audio_max_volume_db: float | None = None


def extract_audio_loudness(video_path: str | Path) -> tuple[float | None, float | None]:
    """Extract mean and max volume in dB using FFmpeg volumedetect filter."""
    result = run_ffmpeg(
        [
            "-i", str(video_path),
            "-af", "volumedetect",
            "-vn", "-sn", "-dn",
            "-f", "null",
            "-",
        ],
        check=False,
    )
    output = result.stderr or ""
    mean_match = re.search(r"mean_volume:\s*(-?[\d.]+)\s*dB", output)
    max_match = re.search(r"max_volume:\s*(-?[\d.]+)\s*dB", output)

    mean_vol = float(mean_match.group(1)) if mean_match else None
    max_vol = float(max_match.group(1)) if max_match else None
    return mean_vol, max_vol


def sample_frames_at_1fps(
    video_path: str | Path,
    target_width: int = 360,
) -> list[tuple[float, np.ndarray]]:
    """Sample one frame per second resized to target_width preserving aspect ratio."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration_s = total_frames / fps if fps > 0 else 0.0

    frames: list[tuple[float, np.ndarray]] = []
    second = 0
    while second < int(duration_s):
        target_frame = int(round(second * fps))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        target_height = int(round(h * (target_width / w)))
        resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        frames.append((float(second), resized))
        second += 1

    cap.release()
    return frames


def analyse_local_metrics(video_path: str | Path) -> LocalClipMetrics:
    """Compute local metrics: duration, fps, resolution, per-second blur, brightness, loudness."""
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(f"Video file does not exist: {path}")

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS)) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s = round(total_frames / fps, 2) if fps > 0 else 0.0
    cap.release()

    sampled = sample_frames_at_1fps(path, target_width=360)
    per_second: list[SecondMetric] = []
    blur_scores: list[float] = []
    brightness_scores: list[float] = []

    for sec, frame in sampled:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blur_val = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        bright_val = float(np.mean(gray))

        per_second.append(
            SecondMetric(
                second=int(sec),
                blur_score=round(blur_val, 2),
                brightness=round(bright_val, 2),
            )
        )
        blur_scores.append(blur_val)
        brightness_scores.append(bright_val)

    mean_blur = round(float(np.mean(blur_scores)), 2) if blur_scores else 0.0
    mean_bright = round(float(np.mean(brightness_scores)), 2) if brightness_scores else 0.0
    mean_vol, max_vol = extract_audio_loudness(path)

    return LocalClipMetrics(
        duration_s=duration_s,
        fps=fps,
        width=width,
        height=height,
        per_second_metrics=per_second,
        mean_blur_score=mean_blur,
        mean_brightness=mean_bright,
        audio_mean_volume_db=mean_vol,
        audio_max_volume_db=max_vol,
    )


def build_safe_fallback_clip_analysis(clip_id: int, duration_s: float) -> ClipAnalysis:
    """Construct safe fallback ClipAnalysis with all moments scored 5."""
    step = 2.0
    moments: list[Moment] = []
    t = 0.0
    duration = max(duration_s, 2.0)
    while t < duration:
        t_end = min(round(t + step, 2), duration)
        moments.append(
            Moment(
                t_start=round(t, 2),
                t_end=t_end,
                appeal=5,
                sharpness=5,
                lighting=5,
                has_food=True,
                has_person=False,
                tag="food footage",
            )
        )
        t = t_end

    return ClipAnalysis(
        clip_id=clip_id,
        moments=moments,
        overall_note="safe fallback due to analysis error",
    )


def frames_to_base64_jpegs(frames: list[tuple[float, np.ndarray]]) -> list[str]:
    """Encode OpenCV frames into base64 JPEG strings."""
    encoded: list[str] = []
    for _sec, frame in frames:
        success, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if success:
            encoded.append(base64.b64encode(buffer).decode("utf-8"))
    return encoded


def analyse_clip_vision(
    clip_id: int,
    video_path: str | Path,
    llm_client: LLMClient,
    local_metrics: LocalClipMetrics | None = None,
) -> ClipAnalysis:
    """Analyze a single clip using vision LLM with one retry and safe fallback."""
    metrics = local_metrics or analyse_local_metrics(video_path)
    sampled = sample_frames_at_1fps(video_path, target_width=360)
    image_b64s = frames_to_base64_jpegs(sampled)

    prompt_base = (
        PROMPT_PATH.read_text(encoding="utf-8")
        if PROMPT_PATH.is_file()
        else "Judge video moments. Return ClipAnalysis JSON."
    )
    prompt = f"{prompt_base}\n\nClip ID: {clip_id}, Duration: {metrics.duration_s}s"

    # Attempt 1
    try:
        return llm_client.generate_json(
            prompt=prompt,
            schema=ClipAnalysis,
            images=image_b64s,
        )
    except (ValidationError, Exception) as e1:
        logger.warning(f"Clip {clip_id} vision analysis attempt 1 failed: {e1}. Retrying once...")
        # Attempt 2 (Retry with error context)
        retry_prompt = f"{prompt}\n\nPrevious attempt failed with error: {e1}. Please return valid ClipAnalysis JSON."
        try:
            return llm_client.generate_json(
                prompt=retry_prompt,
                schema=ClipAnalysis,
                images=image_b64s,
            )
        except (ValidationError, Exception) as e2:
            logger.error(f"Clip {clip_id} vision analysis attempt 2 failed: {e2}. Using safe fallback.")
            return build_safe_fallback_clip_analysis(clip_id, metrics.duration_s)


def analyse_clips_parallel(
    clips: Sequence[tuple[int, str | Path]],
    llm_client: LLMClient,
    max_workers: int = 4,
) -> list[ClipAnalysis]:
    """Analyze multiple clips in parallel using ThreadPoolExecutor."""
    def _worker(item: tuple[int, str | Path]) -> ClipAnalysis:
        cid, path = item
        return analyse_clip_vision(cid, path, llm_client)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(_worker, clips))
    return results
