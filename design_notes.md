# Design Notes — Development Reflection

## The Hardest Part

The hardest part was getting **real-time low-latency audio** to work end-to-end. 

My initial assumption was that the pipeline would be straightforward — record audio, transcribe, call LLM, play response. But every step had hidden latency. Whisper on CPU was slow (2-3 seconds just for transcription). gTTS required an HTTP call to Google's servers for every response. And the biggest issue — I was waiting for the **entire** LLM response to finish before starting TTS, which meant the user waited 4-6 seconds every turn.

The breakthrough came when I stopped thinking about it as a request-response system and started thinking about it as a **pipeline of streams**. Each stage should start outputting as soon as it has *something* — not wait for everything.

---

## A Mistake I Made

The most frustrating bug was with **faster-whisper's generator**.

I upgraded from original Whisper to faster-whisper for the 4x speed improvement. It worked perfectly in isolation. But when integrated into the async FastAPI backend, transcriptions randomly came back empty — even for clear audio.

The bug was subtle: faster-whisper's `model.transcribe()` returns a **lazy generator** for segments. I was doing:

```python
# WRONG — generator returned to async context, consumed outside the thread
segments, info = model.transcribe(audio_path)
text = " ".join(s.text for s in segments)
```

The generator was tied to the model's internal state inside the executor thread. By the time the async event loop consumed it outside the thread, the state was gone — empty results every time.

---

## How I Fixed It

The fix was one word — `list()`:

```python
# CORRECT — force consume the generator INSIDE the thread
segments, info = model.transcribe(audio_path)
text = " ".join(s.text for s in list(segments))  # list() forces evaluation here
```

`list(segments)` forces the entire generator to be consumed immediately inside the executor thread where the model context still exists. After that, it's just a plain Python list — safe to use anywhere.

This taught me something important: when running synchronous code inside `asyncio.run_in_executor()`, anything that returns a lazy iterator tied to internal state must be fully evaluated **before** returning from the executor function.

---

*Total development time: ~48 hours | Stack: FastAPI · LangGraph · Groq · Web Speech API · SQLite*