"""FFmpeg video rendering driven by ad Plan and template configuration."""

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from app.llm.schemas import Plan
from app.pipeline.ass_writer import generate_ass_subtitles
from app.pipeline.ffmpeg_utils import run_ffmpeg, run_ffprobe
from app.pipeline.plan import BusinessContext
from app.pipeline.templates import TemplateConfig, load_template

logger = logging.getLogger(__name__)

MUSIC_DIR = Path(__file__).resolve().parents[2] / "assets" / "music"


def ensure_background_music_track(temp_dir: Path) -> Path:
    """Find a background track in assets/music or synthesize a royalty-free ambient track."""
    if MUSIC_DIR.is_dir():
        for ext in ("*.mp3", "*.wav", "*.m4a"):
            tracks = list(MUSIC_DIR.glob(ext))
            if tracks:
                return tracks[0]

    # Generate a soft warm ambient audio texture (pink noise lowpassed, warm lofi texture)
    synth_music = temp_dir / "ambient_music.mp3"
    run_ffmpeg(
        [
            "-y",
            "-f", "lavfi",
            "-i", "anoisesrc=d=30:c=pink:r=44100,lowpass=f=350",
            "-af", "volume=0.10",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(synth_music),
        ]
    )
    return synth_music


def render_video(
    plan: Plan,
    business: BusinessContext,
    clip_paths: Mapping[int, str | Path],
    output_path: str | Path,
    template: TemplateConfig | None = None,
) -> Path:
    """Render a vertical Reel (1080x1920) conforming to Plan and template rules."""
    tpl = template or load_template(plan.template)
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=out_file.parent) as td_str:
        td = Path(td_str)

        # Step 1: Cut and normalize each segment
        seg_files: list[Path] = []
        for idx, seg in enumerate(plan.segments):
            clip_path = clip_paths.get(seg.clip_id)
            if not clip_path or not Path(clip_path).is_file():
                # Fallback to first available clip
                clip_path = next(iter(clip_paths.values()))

            seg_path = td / f"seg_{idx:03d}.mp4"
            dur = max(0.5, round(seg.end - seg.start, 2))

            # Scale, crop to 1080x1920, 30fps with silent/original audio
            run_ffmpeg(
                [
                    "-y",
                    "-ss", str(seg.start),
                    "-t", str(dur),
                    "-i", str(clip_path),
                    "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1",
                    "-c:v", "libx264",
                    "-preset", "veryfast",
                    "-crf", "22",
                    "-c:a", "aac",
                    "-ar", "44100",
                    "-ac", "2",
                    str(seg_path),
                ]
            )
            seg_files.append(seg_path)

        # Step 2: Concat segments
        concat_txt = td / "concat.txt"
        concat_lines = [f"file '{p.name}'" for p in seg_files]
        concat_txt.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

        raw_concat = td / "raw_concat.mp4"
        run_ffmpeg(
            [
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_txt),
                "-c", "copy",
                str(raw_concat),
            ]
        )

        # Measure concatenated duration
        probe_res = run_ffprobe(
            [
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(raw_concat),
            ]
        )
        try:
            actual_duration = float(probe_res.stdout.strip())
        except (ValueError, TypeError):
            actual_duration = plan.target_duration_s

        # Step 3: Create ASS subtitles
        ass_file = td / "subtitles.ass"
        generate_ass_subtitles(
            hook_text=plan.hook_text,
            on_screen_lines=plan.on_screen_lines,
            offer_text=plan.offer_text,
            cta_text=plan.call_to_action,
            business_name=business.name,
            brand_hex=business.brand_hex,
            target_duration_s=actual_duration,
            output_path=ass_file,
            template_text_config=tpl.text,
            price_inr=plan.price_inr,
        )


        # Step 4: Music track and audio mix
        music_track = ensure_background_music_track(td)
        fade_start = max(0.5, actual_duration - tpl.music.fade_out_s)

        # Escape ass_file relative to td
        brand_hex_clean = business.brand_hex.lstrip("#")
        vf_filters = (
            f"drawbox=x=0:y=ih-14:w=iw:h=14:color=0x{brand_hex_clean}:t=fill,"
            f"subtitles={ass_file.name}"
        )
        audio_filter = (
            f"[1:a]volume={tpl.music.volume},afade=t=out:st={fade_start}:d={tpl.music.fade_out_s}[music];"
            f"[0:a][music]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )

        # Step 5: Final Composite Render
        temp_out = td / "final_reel.mp4"
        run_ffmpeg(
            [
                "-y",
                "-i", str(raw_concat),
                "-stream_loop", "-1",
                "-i", str(music_track),
                "-filter_complex", f"[0:v]{vf_filters}[vout];{audio_filter}",
                "-map", "[vout]",
                "-map", "[aout]",
                "-c:v", "libx264",
                "-crf", "23",
                "-preset", "veryfast",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "128k",
                "-movflags", "+faststart",
                str(temp_out),
            ],
            check=True,
            cwd=td,
        )


        # Step 6: Size check (< 16 MB)
        if temp_out.stat().st_size > 16 * 1024 * 1024:
            logger.warning("Output exceeded 16MB; re-encoding with lower bitrate.")
            compressed_out = td / "compressed.mp4"
            run_ffmpeg(
                [
                    "-y",
                    "-i", str(temp_out),
                    "-c:v", "libx264",
                    "-crf", "27",
                    "-preset", "veryfast",
                    "-c:a", "aac",
                    "-b:a", "96k",
                    "-movflags", "+faststart",
                    str(compressed_out),
                ]
            )
            shutil.copy2(compressed_out, out_file)
        else:
            shutil.copy2(temp_out, out_file)

    return out_file
