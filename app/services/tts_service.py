"""
Text-to-Speech — tries gTTS first (needs internet), falls back to pyttsx3/espeak.
"""
import asyncio
import uuid
import tempfile
import subprocess
from pathlib import Path

from app.utils.logger import get_logger

logger = get_logger(__name__)

TEMP_DIR = Path(tempfile.gettempdir()) / "voice_agent_tts"


def _ensure_dir():
    TEMP_DIR.mkdir(parents=True, exist_ok=True)


def _try_gtts(text: str, output_path: str) -> bool:
    """Try gTTS (requires internet)."""
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(output_path)
        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            logger.info("✅ TTS via gTTS")
            return True
    except Exception as e:
        logger.warning(f"gTTS failed: {e}")
    return False


def _try_espeak(text: str, output_path: str) -> bool:
    """Try espeak (offline, needs espeak installed)."""
    try:
        wav_path = output_path.replace(".mp3", ".wav")
        result = subprocess.run(
            ["espeak", "-w", wav_path, text],
            capture_output=True, timeout=15
        )
        if result.returncode == 0 and Path(wav_path).exists():
            # Convert wav to mp3 using ffmpeg if available
            try:
                subprocess.run(
                    ["ffmpeg", "-y", "-i", wav_path, output_path],
                    capture_output=True, timeout=15
                )
                Path(wav_path).unlink(missing_ok=True)
                if Path(output_path).exists():
                    logger.info("✅ TTS via espeak+ffmpeg")
                    return True
            except Exception:
                # Return wav directly if no ffmpeg
                import shutil
                shutil.copy(wav_path, output_path)
                logger.info("✅ TTS via espeak (wav)")
                return True
    except Exception as e:
        logger.warning(f"espeak failed: {e}")
    return False


def _try_pyttsx3(text: str, output_path: str) -> bool:
    """Try pyttsx3 (offline)."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.save_to_file(text, output_path)
        engine.runAndWait()
        engine.stop()
        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            logger.info("✅ TTS via pyttsx3")
            return True
    except Exception as e:
        logger.warning(f"pyttsx3 failed: {e}")
    return False


def _synthesise_sync(text: str, output_path: str) -> bool:
    """Try all TTS engines in order."""
    if _try_gtts(text, output_path):
        return True
    if _try_espeak(text, output_path):
        return True
    if _try_pyttsx3(text, output_path):
        return True
    logger.error("All TTS engines failed")
    return False


async def synthesise(text: str, lang: str = "en") -> dict:
    if not text.strip():
        return {"audio_path": None, "success": False, "error": "Empty text"}

    _ensure_dir()
    output_path = str(TEMP_DIR / f"{uuid.uuid4().hex}.mp3")

    logger.info(f"TTS synthesising: '{text[:60]}'")

    try:
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(None, _synthesise_sync, text, output_path)

        if not success or not Path(output_path).exists():
            return {"audio_path": None, "success": False, "error": "All TTS engines failed"}

        size = Path(output_path).stat().st_size
        logger.info(f"✅ TTS complete → {output_path} ({size} bytes)")
        return {"audio_path": output_path, "success": True, "error": None}

    except Exception as e:
        logger.error(f"TTS error: {e}")
        return {"audio_path": None, "success": False, "error": str(e)}


def cleanup(path: str | None):
    if not path:
        return
    try:
        Path(path).unlink(missing_ok=True)
    except Exception:
        pass