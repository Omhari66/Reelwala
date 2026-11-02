"""Generate synthetic vertical test clips with FFmpeg or import real clips."""

import argparse
import shutil
import sys
from pathlib import Path
from typing import Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.pipeline.ffmpeg_utils import run_ffmpeg  # noqa: E402


def generate_synthetic_fixtures(out_dir: Path | str, force: bool = False) -> list[Path]:
    """Generate 3 vertical synthetic MP4 clips for testing."""
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    clip1 = target_dir / "clip1_sharp.mp4"
    clip2 = target_dir / "clip2_blurred.mp4"
    clip3 = target_dir / "clip3_dark.mp4"

    clips = [clip1, clip2, clip3]
    if not force and all(c.is_file() and c.stat().st_size > 1000 for c in clips):
        return clips

    # Clip 1: Sharp vertical video (testsrc scaled and padded to 1080x1920) + 1000Hz sine audio
    run_ffmpeg(
        [
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=5:size=1080x1920:rate=30",
            "-f", "lavfi",
            "-i", "sine=frequency=1000:duration=5:sample_rate=44100",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            str(clip1),
        ]
    )

    # Clip 2: Blurred vertical video (boxblur) + 440Hz sine audio
    run_ffmpeg(
        [
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=5:size=1080x1920:rate=30",
            "-f", "lavfi",
            "-i", "sine=frequency=440:duration=5:sample_rate=44100",
            "-vf", "boxblur=15:5",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            str(clip2),
        ]
    )

    # Clip 3: Dark vertical video (color=black with low brightness test pattern) + 220Hz sine audio
    run_ffmpeg(
        [
            "-y",
            "-f", "lavfi",
            "-i", "testsrc=duration=5:size=1080x1920:rate=30",
            "-f", "lavfi",
            "-i", "sine=frequency=220:duration=5:sample_rate=44100",
            "-vf", "eq=brightness=-0.6:contrast=0.4",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            str(clip3),
        ]
    )

    return clips


def import_real_clips(real_paths: Sequence[str | Path], out_dir: Path | str) -> list[Path]:
    """Copy provided real clips to target fixture directory."""
    target_dir = Path(out_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    imported: list[Path] = []
    for idx, path_str in enumerate(real_paths, start=1):
        src = Path(path_str)
        if not src.is_file():
            raise FileNotFoundError(f"Source clip not found: {src}")
        dest = target_dir / f"real_clip_{idx}{src.suffix}"
        shutil.copy2(src, dest)
        imported.append(dest)
    return imported


def main() -> None:
    """CLI entrypoint for fixture generation."""
    parser = argparse.ArgumentParser(description="Generate or import test clip fixtures.")
    parser.add_argument(
        "--out-dir",
        default="tests/fixtures/synthetic",
        help="Output directory for test fixtures",
    )
    parser.add_argument(
        "--real-clips",
        nargs="*",
        default=[],
        help="Optional paths to real video clips to import",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force regeneration even if fixtures exist",
    )
    args = parser.parse_args()

    if args.real_clips:
        results = import_real_clips(args.real_clips, args.out_dir)
        print(f"Imported {len(results)} real clips into {args.out_dir}")
    else:
        results = generate_synthetic_fixtures(args.out_dir, force=args.force)
        print(f"Generated {len(results)} synthetic clips in {args.out_dir}:")
        for clip in results:
            print(f" - {clip.name} ({clip.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
