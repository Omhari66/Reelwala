"""Pipeline step: Download and normalize incoming media assets into video clips."""

from pathlib import Path

from app.pipeline.ffmpeg_utils import run_ffmpeg

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def is_image_file(path: str | Path) -> bool:
    """Return True if path has an image file extension."""
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS


def convert_image_to_still_clip(
    image_path: str | Path,
    output_path: str | Path,
    duration_s: float = 3.0,
) -> Path:
    """Convert a static image to a 3-second vertical 1080x1920 clip with Ken Burns zoom."""
    src = Path(image_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Ken Burns slow zoom (scale and zoompan filter)
    total_frames = int(round(duration_s * 30))
    vf_filter = (
        f"scale=1080:1920:force_original_aspect_ratio=increase,"
        f"zoompan=z='min(zoom+0.0015,1.15)':d={total_frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,"
        f"crop=1080:1920"
    )

    run_ffmpeg(
        [
            "-y",
            "-loop", "1",
            "-i", str(src),
            "-f", "lavfi",
            "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-vf", vf_filter,
            "-t", str(duration_s),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "128k",
            "-shortest",
            str(out),
        ]
    )
    return out


def normalize_media_clip(media_path: str | Path, output_dir: str | Path) -> Path:
    """Ensure media asset is a video clip; convert static images into 3s clips."""
    src = Path(media_path)
    if not src.is_file():
        raise FileNotFoundError(f"Source media not found: {src}")

    if is_image_file(src):
        dest = Path(output_dir) / f"{src.stem}_clip.mp4"
        return convert_image_to_still_clip(src, dest, duration_s=3.0)

    return src
