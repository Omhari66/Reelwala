"""FFmpeg and ffprobe binary discovery and process execution utilities."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Sequence


def get_ffmpeg_path() -> str:
    """Find and return path to ffmpeg executable."""
    # 1. Environment variable override
    env_path = os.getenv("FFMPEG_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    # 2. Virtual environment Scripts directory
    venv_dir = Path(__file__).resolve().parents[2] / ".venv" / "Scripts"
    candidate = venv_dir / "ffmpeg.exe"
    if candidate.is_file():
        return str(candidate)

    # 3. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    raise FileNotFoundError("FFmpeg executable not found in PATH or .venv/Scripts")


def get_ffprobe_path() -> str:
    """Find and return path to ffprobe executable."""
    env_path = os.getenv("FFPROBE_PATH")
    if env_path and Path(env_path).is_file():
        return env_path

    venv_dir = Path(__file__).resolve().parents[2] / ".venv" / "Scripts"
    candidate = venv_dir / "ffprobe.exe"
    if candidate.is_file():
        return str(candidate)

    found = shutil.which("ffprobe")
    if found:
        return found

    raise FileNotFoundError("ffprobe executable not found in PATH or .venv/Scripts")


def run_ffmpeg(
    args: Sequence[str],
    check: bool = True,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute ffmpeg with argument list (never shell=True)."""
    ffmpeg_exe = get_ffmpeg_path()
    cmd = [ffmpeg_exe, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        cwd=str(cwd) if cwd else None,
    )


def run_ffprobe(
    args: Sequence[str],
    check: bool = True,
    cwd: str | Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute ffprobe with argument list (never shell=True)."""
    ffprobe_exe = get_ffprobe_path()
    cmd = [ffprobe_exe, *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=check,
        cwd=str(cwd) if cwd else None,
    )

