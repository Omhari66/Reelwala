"""Optional voice-note audio transcription guarded behind ENABLE_VOICE_NOTES."""

import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


def transcribe_voice_note(audio_path: str | Path) -> str | None:
    """Transcribe an inbound voice-note audio file using faster-whisper if enabled and installed."""
    if not settings.ENABLE_VOICE_NOTES:
        logger.info("Voice note transcription skipped because ENABLE_VOICE_NOTES is False.")
        return None

    path = Path(audio_path)
    if not path.is_file():
        logger.warning(f"Audio file not found for transcription: {path}")
        return None

    try:
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        model = WhisperModel("tiny", device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(path))
        transcription = " ".join([seg.text.strip() for seg in segments]).strip()
        return transcription or None
    except ImportError:
        logger.info("faster-whisper is not installed. Voice note transcription unavailable.")
        return None
    except Exception as e:
        logger.error(f"Failed to transcribe audio file {path}: {e}")
        return None
