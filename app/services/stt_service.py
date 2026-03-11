"""
STT — faster-whisper (4x faster than original whisper).
Falls back to original whisper if faster-whisper not available.
"""
import asyncio
from pathlib import Path
from functools import lru_cache
from app.config import settings
from app.utils.logger import get_logger

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_model():
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel(settings.WHISPER_MODEL, device="cpu", compute_type="int8")
        logger.info(f"✅ faster-whisper '{settings.WHISPER_MODEL}' loaded")
        return ("faster", model)
    except Exception as e:
        logger.warning(f"faster-whisper not available ({e}), using original whisper")

    import whisper
    model = whisper.load_model(settings.WHISPER_MODEL)
    logger.info(f"✅ whisper '{settings.WHISPER_MODEL}' loaded")
    return ("whisper", model)


def _transcribe_sync(audio_path: str) -> dict:
    kind, model = _load_model()

    if kind == "faster":
        segments, info = model.transcribe(
            audio_path,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        # ⚠️ Must consume generator HERE inside the thread, not lazily outside
        text = " ".join(s.text for s in list(segments)).strip()
        return {"text": text, "language": info.language}

    else:
        result = model.transcribe(audio_path, fp16=False)
        return {
            "text": result.get("text", "").strip(),
            "language": result.get("language", "en"),
        }


async def transcribe(audio_path: str | Path) -> dict:
    audio_path = str(audio_path)
    logger.info(f"STT: {audio_path}")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _transcribe_sync, audio_path)
        text     = result["text"]
        language = result["language"]

        if not text:
            return {"text": "", "language": language, "success": False, "error": "No speech detected"}

        logger.info(f"✅ STT | lang={language} | '{text[:80]}'")
        return {"text": text, "language": language, "success": True, "error": None}

    except Exception as e:
        logger.error(f"STT error: {e}")
        return {"text": "", "language": "en", "success": False, "error": str(e)}


def preload():
    try:
        _load_model()
    except Exception as e:
        logger.warning(f"STT preload skipped: {e}")