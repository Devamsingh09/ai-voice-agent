# 🎙️ AI Voice Agent

> **Real-time voice conversation with AI — ChatGPT Voice Mode style**  
> Zero audio files. Zero latency. Speak → AI thinks → AI speaks back.

---

## ⚡ How It Works — Simple Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER                                  │
│                                                                 │
│   🎤 You Speak                                                  │
│       │                                                         │
│       ▼                                                         │
│   ┌─────────────────────┐                                       │
│   │  Web Speech API     │  ← Built into Chrome/Edge            │
│   │  SpeechRecognition  │    No upload. No server.             │
│   │  (Real-time STT)    │    Text ready instantly.             │
│   └────────┬────────────┘                                       │
│            │  text                                              │
└────────────┼────────────────────────────────────────────────────┘
             │
             │  HTTP POST /chat/stream
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FASTAPI BACKEND                            │
│                                                                 │
│   ┌─────────────────────┐                                       │
│   │    LangGraph        │  ← Manages conversation flow         │
│   │    State Machine    │    + memory per session              │
│   └────────┬────────────┘                                       │
│            │                                                    │
│            ▼                                                    │
│   ┌─────────────────────┐                                       │
│   │   Groq API          │  ← LLaMA 3.1 8B Instant             │
│   │   LLaMA 3.1 8B      │    10x faster than OpenAI           │
│   │   (Streaming LLM)   │    Tokens stream back immediately    │
│   └────────┬────────────┘                                       │
│            │  token stream (SSE)                               │
│            ▼                                                    │
│   ┌─────────────────────┐                                       │
│   │   SQLite Memory     │  ← Full conversation history         │
│   │   (LangGraph        │    Persists across sessions          │
│   │    Checkpointer)    │    Per thread_id                     │
│   └─────────────────────┘                                       │
│                                                                 │
└────────────┼────────────────────────────────────────────────────┘
             │  SSE token stream
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        BROWSER                                  │
│                                                                 │
│   Tokens arrive → build sentence → sentence complete?          │
│                                          │                      │
│                                          ▼                      │
│                              ┌───────────────────────┐         │
│                              │  Web Speech API        │        │
│                              │  SpeechSynthesis       │        │
│                              │  (Browser TTS)         │        │
│                              │  Zero network call     │        │
│                              └───────────────────────┘         │
│                                          │                      │
│                                          ▼                      │
│                                   🔊 You Hear It               │
│                              (while LLM still generating       │
│                               the next sentence!)              │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🗺️ Full Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   USER                                                               │
│    │                                                                 │
│    │ speaks                                                          │
│    ▼                                                                 │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │                    STREAMLIT UI                          │       │
│  │                  (streamlit_app.py)                      │       │
│  │                                                          │       │
│  │  ┌─────────────────┐      ┌──────────────────────────┐  │       │
│  │  │ SpeechRecognition│      │    SpeechSynthesis       │  │       │
│  │  │  Web Speech API  │      │     Web Speech API       │  │       │
│  │  │                  │      │                          │  │       │
│  │  │ • Real-time STT  │      │ • Zero-latency TTS       │  │       │
│  │  │ • No upload      │      │ • Sentence-by-sentence   │  │       │
│  │  │ • Interim results│      │ • Voice selector         │  │       │
│  │  │ • ~0ms latency   │      │ • ~0ms latency           │  │       │
│  │  └────────┬─────────┘      └────────────▲─────────────┘  │       │
│  │           │ text                        │ text sentences  │       │
│  └───────────┼─────────────────────────────┼────────────────┘       │
│              │                             │                         │
│              │  POST /chat/stream          │  SSE token stream       │
│              ▼                             │                         │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │                  FASTAPI BACKEND                         │       │
│  │                    (app/main.py)                         │       │
│  │                                                          │       │
│  │  Endpoints:                                              │       │
│  │  • POST /chat/stream   ← main voice endpoint            │       │
│  │  • POST /voice/input   ← fallback (Whisper STT)         │       │
│  │  • POST /voice/text    ← text → TTS fallback            │       │
│  │  • GET  /history/{id}  ← load conversation              │       │
│  │  • DELETE /history/{id}← clear session                  │       │
│  │  • GET  /sessions      ← list all threads               │       │
│  │  • GET  /health        ← status check                   │       │
│  │           │                                              │       │
│  │           ▼                                              │       │
│  │  ┌────────────────────────────────────────────────┐     │       │
│  │  │            LANGGRAPH AGENT                     │     │       │
│  │  │            (app/graph/agent.py)                │     │       │
│  │  │                                                │     │       │
│  │  │  StateGraph:                                   │     │       │
│  │  │  [START] → [llm_node] → [END]                 │     │       │
│  │  │                                                │     │       │
│  │  │  AgentState:                                   │     │       │
│  │  │  { messages: Annotated[list, add_messages] }  │     │       │
│  │  │                                                │     │       │
│  │  │  stream_sentences() → sentence generator      │     │       │
│  │  └───────────┬────────────────────────────────────┘     │       │
│  │              │                                           │       │
│  │     ┌────────┴──────────┐                               │       │
│  │     │                   │                               │       │
│  │     ▼                   ▼                               │       │
│  │  ┌──────────┐    ┌─────────────┐                        │       │
│  │  │  GROQ    │    │   SQLITE    │                        │       │
│  │  │  API     │    │   MEMORY    │                        │       │
│  │  │          │    │             │                        │       │
│  │  │ LLaMA    │    │ LangGraph   │                        │       │
│  │  │ 3.1 8B   │    │ Checkpointer│                        │       │
│  │  │ Instant  │    │             │                        │       │
│  │  │          │    │ data/       │                        │       │
│  │  │ Streaming│    │ memory.db   │                        │       │
│  │  └──────────┘    └─────────────┘                        │       │
│  └──────────────────────────────────────────────────────────┘       │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘


FALLBACK SERVICES (when browser APIs not available):
┌─────────────────────────────────────────────────────┐
│  app/services/stt_service.py                        │
│  ┌─────────────────────────────────────────────┐   │
│  │  faster-whisper (primary)                   │   │
│  │  • int8 quantized, 4x faster than whisper   │   │
│  │  • VAD filter (silence skip)                │   │
│  │  • beam_size=1 (fastest)                    │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │  openai-whisper (fallback)                  │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  app/services/tts_service.py                        │
│  ┌─────────────────────────────────────────────┐   │
│  │  gTTS (primary fallback)                    │   │
│  │  • Google TTS API                           │   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │  pyttsx3 / espeak (offline fallback)        │   │
│  └─────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ Tools & Libraries

| Tool | Purpose | Why This One |
|------|---------|--------------|
| **FastAPI** | Backend web server | Async, fast, auto API docs |
| **Uvicorn** | ASGI server | Runs FastAPI |
| **LangGraph** | Conversation state machine | Built-in memory, clean graph flow |
| **LangChain** | LLM abstraction layer | Works with any LLM provider |
| **Groq API** | LLM inference | 10x faster than OpenAI, free tier |
| **LLaMA 3.1 8B** | Language model | Fast, smart, free via Groq |
| **SQLite** | Conversation memory DB | Zero setup, file-based, persistent |
| **langgraph-checkpoint-sqlite** | SQLite checkpointer for LangGraph | Auto memory per thread |
| **Web Speech API** | STT + TTS in browser | Zero latency, no server needed |
| **faster-whisper** | Server-side STT fallback | 4x faster than Whisper, int8 CPU |
| **openai-whisper** | STT fallback #2 | Offline, accurate |
| **gTTS** | Server-side TTS fallback | Free, Google quality |
| **Streamlit** | UI framework | Python-native, fast to build |
| **httpx** | HTTP client | Async, supports SSE streaming |
| **aiofiles** | Async file I/O | Non-blocking file operations |
| **python-dotenv** | .env file loader | Keep API keys out of code |
| **Pydantic** | Request validation | Type-safe API inputs |

---

## 🚀 Latency Evolution

```
VERSION 1 — File-based (Slow)
─────────────────────────────
Upload WAV (1s) → Whisper CPU (2-3s) → Full LLM wait (2s) → gTTS HTTP (1s) → Download MP3 (0.5s)
Total: 6-8 seconds 😴

VERSION 2 — Optimised Server Pipeline
──────────────────────────────────────
faster-whisper int8 (0.5s) → Sentence streaming → gTTS per sentence (0.8s each)
Total: 2-3 seconds 🙂

VERSION 3 — Browser-Native (Current)
─────────────────────────────────────
SpeechRecognition (0ms) → Groq first token (300ms) → SpeechSynthesis (0ms)
Total: ~400ms 🚀
```

---

## 📁 Project Structure

```
ai-voice-agent-v2/
│
├── .env                        ← API keys (never commit this)
├── .env.example                ← Template for .env
├── requirements.txt            ← All Python dependencies
├── streamlit_app.py            ← Entire UI (HTML/JS/CSS embedded)
│
├── app/
│   ├── __init__.py
│   ├── main.py                 ← FastAPI — all endpoints
│   ├── config.py               ← Settings loaded from .env
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   └── agent.py            ← LangGraph agent + sentence streaming
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── stt_service.py      ← faster-whisper STT (fallback)
│   │   └── tts_service.py      ← gTTS TTS (fallback)
│   │
│   └── utils/
│       ├── __init__.py
│       └── logger.py           ← Logging setup
│
└── data/
    └── memory.db               ← SQLite — auto created on first run
```

---

## ⚙️ Setup & Run

### 1. Prerequisites
```bash
# Python 3.10+
python --version

# ffmpeg (for audio processing)
# Mac:
brew install ffmpeg
# Ubuntu:
sudo apt install ffmpeg
# Windows:
choco install ffmpeg
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
pip install faster-whisper          # recommended for speed
pip install audio-recorder-streamlit
```

### 3. Configure
```bash
# Create .env file
echo "GROQ_API_KEY=your_key_here" > .env

# Get free API key from:
# https://console.groq.com
```

### 4. Run
```bash
# Terminal 1 — Backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — UI
streamlit run streamlit_app.py
```

### 5. Open browser
```
http://localhost:8501
```

---

## 🔑 Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | required | Get free at console.groq.com |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | LLM model to use |
| `WHISPER_MODEL` | `base` | tiny/base/small/medium |
| `DB_PATH` | `./data/memory.db` | SQLite database path |
| `APP_PORT` | `8000` | Backend port |

---

## 🎮 How to Use

| Action | What to Do |
|--------|-----------|
| **Start talking** | Click the mic button (bottom center) |
| **Stop talking** | Click mic again, or pause 2 seconds |
| **Interrupt AI** | Click mic while AI is speaking |
| **Type instead** | Use text box at bottom |
| **New session** | Click `＋ new` (clears memory) |
| **Change AI voice** | Use voice dropdown in bottom bar |
| **Clear history** | Click `✕ clear` |

---

## 🧠 Key Concepts

### Thread ID
Every conversation has a unique `thread_id`. This is how LangGraph stores separate memories for different sessions. Share the same thread_id = same conversation history.

### Sentence Streaming
The LLM streams tokens one by one. The backend splits them at sentence boundaries (`. ! ?`) and the browser speaks each sentence the moment it's complete — while the LLM is still generating the next one. This is why it feels instant.

### SSE (Server-Sent Events)
Instead of waiting for the full response (HTTP polling), the backend pushes each token to the browser as it's generated. One-way real-time stream from server → client.

---

## 🔧 API Endpoints

```
GET  /health              → Status check
POST /chat/stream         → Main: text in, SSE token stream out
POST /voice/input         → Fallback: audio file in, MP3 out
POST /voice/text          → Fallback: text in, MP3 out
POST /voice/stream        → Streaming: audio in, SSE audio chunks out
GET  /history/{thread_id} → Load conversation from SQLite
DEL  /history/{thread_id} → Clear conversation
GET  /sessions            → List all thread IDs
```

---

## 📝 Requirements.txt

```
fastapi
uvicorn[standard]
python-multipart
aiofiles
langchain
langgraph
langchain-groq
langchain-community
langgraph-checkpoint-sqlite
openai-whisper
faster-whisper
ffmpeg-python
gTTS
pydub
streamlit
audio-recorder-streamlit
httpx
python-dotenv
pydantic
```

---

*Built with ❤️ — FastAPI + LangGraph + Groq + Web Speech API*

---

## 🛡️ Edge Cases I Considered

### 1. STT Returns Empty or Garbage Text
**Problem:** User speaks too softly, too far from mic, or there's background noise. Whisper transcribes it as empty string or random gibberish like `"..."` or `" "`.

**How it's handled:**
- `stt_service.py` checks if transcribed text is empty after stripping whitespace
- Returns `success: False` with error `"No speech detected"`
- Backend returns `HTTP 422` — frontend shows nothing, doesn't send garbage to LLM
- `vad_filter=True` in faster-whisper automatically skips silent audio segments before even trying to transcribe

```python
if not text:
    return {"success": False, "error": "No speech detected"}
```

---

### 2. Long Audio / Very Long User Message
**Problem:** User records a 2-minute voice note. Whisper takes 30+ seconds to transcribe it. Request times out. Or LLM gets a 500-word input and generates a 400-token response — TTS takes forever.

**How it's handled:**
- File size hard limit: `25MB` check before processing
- `max_tokens=200` on LLM — forces short responses even for long inputs
- System prompt explicitly says: *"Keep responses SHORT — 1 to 3 sentences maximum"*
- `timeout=90` on all backend calls — won't hang indefinitely
- faster-whisper with `beam_size=1` processes long audio faster than standard Whisper

```python
if len(content) > 25 * 1024 * 1024:
    raise HTTPException(400, "File too large (max 25MB)")
```

---

### 3. Network Interruption Mid-Stream
**Problem:** User's internet drops while LLM is streaming tokens via SSE. Connection breaks halfway. Frontend gets partial response. Or backend loses connection to Groq API mid-generation.

**How it's handled:**
- SSE stream wrapped in `try/except` — if connection drops, error is logged, partial response is discarded cleanly
- Frontend `fetch` with SSE reader catches network errors gracefully
- LangGraph checkpointer saves state to SQLite **after** full response — partial responses don't corrupt memory
- Browser Web Speech API handles mic disconnects automatically — just stops recognition, no crash

```python
try:
    for chunk in agent.stream_response(user_text, thread_id):
        yield f"data: {chunk}\n\n"
except Exception as e:
    logger.error(f"Stream broken: {e}")
    yield "data: [DONE]\n\n"  # always close stream cleanly
```

---

### 4. Groq API Rate Limit / Downtime
**Problem:** Groq free tier has rate limits. During peak usage, API returns `429 Too Many Requests`. Or Groq has an outage.

**How it's handled:**
- `try/except` around every LLM call in `agent.py`
- On error: yields a friendly fallback message instead of crashing
- HTTP error code properly propagated to frontend
- System is designed to swap LLM providers easily — just change `GROQ_MODEL` in `.env` or swap `ChatGroq` for `ChatOpenAI`

```python
except Exception as e:
    logger.error(f"LLM error: {e}")
    yield f"Sorry, I had an error. Please try again."
```

---

### 5. Duplicate Audio Processing (Same Recording Sent Twice)
**Problem:** `audio_recorder_streamlit` sometimes fires the same audio bytes twice on re-render. Without deduplication, same message gets sent to LLM twice, causing duplicate responses and double memory entries.

**How it's handled:**
- `hash(audio_bytes)` computed for every recording
- Compared against `st.session_state.prev_audio_hash`
- If same hash — skip processing entirely
- Ensures idempotent behaviour even on Streamlit reruns

```python
audio_hash = hash(audio_bytes)
if audio_hash != st.session_state.prev_audio_hash:
    st.session_state.prev_audio_hash = audio_hash
    # process...
```

---