"""
AI Voice Agent — FastAPI Backend (low-latency version)

Key optimisations:
- faster-whisper for STT (4x faster)
- Sentence-by-sentence TTS: audio starts before LLM finishes
- All audio returned as bytes in memory (no FileResponse lag)
- Short LLM responses (max 200 tokens)
"""
import uuid
import asyncio
import aiofiles
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.graph.agent import get_agent
from app.services import stt_service, tts_service
from app.utils.logger import get_logger

logger = get_logger(__name__)

SUPPORTED_AUDIO = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".webm"}
TEMP_DIR = Path(tempfile.gettempdir()) / "voice_agent_input"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 Starting AI Voice Agent (low-latency mode)...")

    from app.config import settings

    print("GROQ KEY LENGTH:", len(settings.GROQ_API_KEY))
    print("GROQ KEY START:", settings.GROQ_API_KEY[:10])

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    get_agent()
    stt_service.preload()

    logger.info("✅ Ready!")
    yield


app = FastAPI(title="AI Voice Agent", version="2.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ChatRequest(BaseModel):
    text: str
    thread_id: str = ""


def _tid(thread_id: str) -> str:
    return thread_id.strip() or str(uuid.uuid4())


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    from app.config import settings
    return {
        "status": "ok", "version": "2.1.0",
        "llm": settings.GROQ_MODEL,
        "stt": f"faster-whisper-{settings.WHISPER_MODEL}",
        "tts": "gTTS",
    }


# ── Fast voice input ───────────────────────────────────────────────────────────

@app.post("/voice/input")
async def voice_input(
    audio: UploadFile = File(...),
    thread_id: str = Form(""),
    return_audio: str = Form("true"),
):
    """
    Low-latency pipeline:
    Audio → faster-whisper STT → Groq LLM (sentence stream) → gTTS per sentence → combined MP3
    """
    thread_id = _tid(thread_id)
    ext = Path(audio.filename or "audio.wav").suffix.lower()
    if ext not in SUPPORTED_AUDIO:
        raise HTTPException(400, f"Unsupported format '{ext}'")

    temp_input = TEMP_DIR / f"{uuid.uuid4().hex}{ext}"
    try:
        content = await audio.read()
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(400, "File too large (max 25MB)")

        async with aiofiles.open(temp_input, "wb") as f:
            await f.write(content)

        # ── STT ───────────────────────────────────────────────────────────────
        stt_result = await stt_service.transcribe(temp_input)
        if not stt_result["success"]:
            raise HTTPException(422, f"STT failed: {stt_result['error']}")

        user_text = stt_result["text"]
        language  = stt_result["language"]
        logger.info(f"STT: '{user_text}'")

        # ── LLM + TTS sentence-by-sentence ────────────────────────────────────
        agent = get_agent()

        if return_audio.lower() == "true":
            # Collect sentences and synthesise each in parallel with generation
            sentences = []
            audio_chunks = []

            for sentence in agent.stream_sentences(user_text, thread_id):
                sentences.append(sentence)
                logger.info(f"TTS sentence: '{sentence}'")
                tts_result = await tts_service.synthesise(sentence)
                if tts_result["success"]:
                    chunk_bytes = Path(tts_result["audio_path"]).read_bytes()
                    tts_service.cleanup(tts_result["audio_path"])
                    audio_chunks.append(chunk_bytes)

            full_response = " ".join(sentences)
            full_audio    = b"".join(audio_chunks)

            if full_audio:
                return Response(
                    content=full_audio,
                    media_type="audio/mpeg",
                    headers={
                        "X-Thread-ID":        thread_id,
                        "X-Transcribed-Text": user_text[:200],
                        "X-AI-Response":      full_response[:200],
                        "X-Detected-Language": language,
                    },
                )

        # Fallback: text only
        full_response = "".join(agent.stream_response(user_text, thread_id))
        return JSONResponse({
            "thread_id":       thread_id,
            "transcribed_text": user_text,
            "ai_response":     full_response,
            "audio_available": False,
        })

    finally:
        tts_service.cleanup(str(temp_input))


# ── Text input ─────────────────────────────────────────────────────────────────

@app.post("/voice/text")
async def voice_text(request: ChatRequest, return_audio: bool = True):
    thread_id = _tid(request.thread_id)
    agent = get_agent()

    if return_audio:
        sentences    = []
        audio_chunks = []

        for sentence in agent.stream_sentences(request.text, thread_id):
            sentences.append(sentence)
            tts_result = await tts_service.synthesise(sentence)
            if tts_result["success"]:
                chunk_bytes = Path(tts_result["audio_path"]).read_bytes()
                tts_service.cleanup(tts_result["audio_path"])
                audio_chunks.append(chunk_bytes)

        full_response = " ".join(sentences)
        full_audio    = b"".join(audio_chunks)

        if full_audio:
            return Response(
                content=full_audio,
                media_type="audio/mpeg",
                headers={
                    "X-Thread-ID":   thread_id,
                    "X-AI-Response": full_response[:200],
                },
            )

    full_response = "".join(agent.stream_response(request.text, thread_id))
    return JSONResponse({"thread_id": thread_id, "ai_response": full_response, "audio_available": False})


# ── Chat stream (SSE) ──────────────────────────────────────────────────────────

@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    if not request.text.strip():
        raise HTTPException(400, "Empty text")

    thread_id = _tid(request.thread_id)
    agent = get_agent()

    def event_stream():
        yield f"data: [THREAD_ID:{thread_id}]\n\n"
        for chunk in agent.stream_response(request.text, thread_id):
            yield f"data: {chunk.replace(chr(10), ' ')}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Thread-ID": thread_id})


# ── History / sessions ─────────────────────────────────────────────────────────

@app.get("/history/{thread_id}")
async def get_history(thread_id: str):
    history = get_agent().get_history(thread_id)
    return {"thread_id": thread_id, "message_count": len(history), "messages": history}


@app.delete("/history/{thread_id}")
async def clear_history(thread_id: str):
    ok = get_agent().clear_history(thread_id)
    return {"thread_id": thread_id, "cleared": ok}


@app.get("/sessions")
async def list_sessions():
    sessions = get_agent().list_sessions()
    return {"session_count": len(sessions), "sessions": sessions}
