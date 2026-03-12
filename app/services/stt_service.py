"""
STT Service — fallback for /voice/input endpoint
Primary STT is browser Web Speech API (zero latency, no server needed)
This is only used when audio file is uploaded directly (Telegram bot etc.)
"""
import asyncio
from pathlib import Path
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _transcribe_sync(audio_path: str) -> dict:
    # Try faster-whisper first
    try:
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            audio_path, beam_size=1, vad_filter=True
        )
        text = " ".join(s.text for s in list(segments)).strip()
        return {"text": text, "language": info.language}
    except Exception as e:
        logger.warning(f"faster-whisper failed: {e}")

    # Try original whisper
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, fp16=False)
        return {"text": result.get("text", "").strip(), "language": "en"}
    except Exception as e:
        logger.warning(f"whisper failed: {e}")

    return {"text": "", "language": "en"}


async def transcribe(audio_path: str | Path) -> dict:
    audio_path = str(audio_path)
    logger.info(f"STT: {audio_path}")
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, _transcribe_sync, audio_path)
        text = result["text"]
        if not text:
            return {"text": "", "language": "en", "success": False,
                    "error": "No speech detected — Whisper not available on server. Use browser mic."}
        logger.info(f"✅ STT: '{text[:80]}'")
        return {"text": text, "language": result["language"], "success": True, "error": None}
    except Exception as e:
        logger.error(f"STT error: {e}")
        return {"text": "", "language": "en", "success": False, "error": str(e)}


def preload():
    logger.info("STT: browser Web Speech API is primary — server STT is fallback only")