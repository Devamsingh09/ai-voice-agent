"""
AI Voice Agent - Zero latency using browser Web Speech API
- STT: Browser SpeechRecognition (real-time, no server round trip)
- LLM: Groq via backend streaming SSE  
- TTS: Browser SpeechSynthesis (instant, no server round trip)
"""
import uuid
import httpx
import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(
    page_title="Voice Agent",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');
  html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
  .stApp { background: #080810; color: #e0e0f0; }
  header[data-testid="stHeader"] { display: none; }
  section[data-testid="stSidebar"] { display: none; }
  .block-container { padding: 1rem 1rem 2rem 1rem; max-width: 860px; }
  .session-pill {
    display: inline-flex; align-items: center;
    background: #0e0e1e; border: 1px solid #1a1a2e; border-radius: 20px;
    padding: 4px 12px; font-family: 'Syne', sans-serif;
    font-size: 0.7rem; color: #33334a; letter-spacing: 1px;
  }
  .stButton > button {
    background: #00d4aa15 !important; border: 1px solid #00d4aa44 !important;
    color: #00d4aa !important; border-radius: 50px !important;
    font-family: 'Syne', sans-serif !important; font-size: 0.78rem !important; font-weight: 600 !important;
  }
  .stButton > button:hover { background: #00d4aa25 !important; border-color: #00d4aa88 !important; }
</style>
""", unsafe_allow_html=True)

if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())[:8]

BACKEND = "http://localhost:8000"

def check_backend():
    try:
        return httpx.get(f"{BACKEND}/health", timeout=2).status_code == 200
    except:
        return False

backend_ok = check_backend()

# Top bar
col1, col2, col3 = st.columns([4, 1, 1])
with col1:
    st.markdown(f'<div class="session-pill">⬡ {st.session_state.thread_id}</div>', unsafe_allow_html=True)
with col2:
    if st.button("＋ new"):
        st.session_state.thread_id = str(uuid.uuid4())[:8]
        st.rerun()
with col3:
    if st.button("✕ clear"):
        try: httpx.delete(f"{BACKEND}/history/{st.session_state.thread_id}", timeout=3)
        except: pass
        st.rerun()

if not backend_ok:
    st.error("⚠ Backend offline — run: uvicorn app.main:app --reload --port 8000")

# The entire voice interface is one self-contained HTML component
VOICE_APP = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Sans:wght@300;400;500&display=swap');

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #080810; color: #e0e0f0;
    font-family: 'DM Sans', sans-serif;
    min-height: 100vh; display: flex; flex-direction: column;
  }}

  /* ── Conversation ── */
  #conversation {{
    flex: 1; overflow-y: auto; padding: 16px 12px 140px 12px;
    display: flex; flex-direction: column; gap: 10px;
    max-height: calc(100vh - 160px);
  }}

  .msg {{ display: flex; gap: 10px; animation: fadeIn 0.2s ease; }}
  @keyframes fadeIn {{ from {{ opacity:0; transform:translateY(4px) }} to {{ opacity:1; transform:none }} }}

  .msg.user  {{ justify-content: flex-end; }}
  .msg.ai    {{ justify-content: flex-start; align-items: flex-end; }}

  .bubble {{
    padding: 10px 15px; border-radius: 18px;
    max-width: 80%; font-size: 0.92rem; line-height: 1.6;
  }}
  .msg.user .bubble {{
    background: #13132a; border: 1px solid #2a2a4a;
    border-radius: 18px 18px 4px 18px; color: #b0b0d8;
  }}
  .msg.ai .bubble {{
    background: #0c1a16; border: 1px solid #00e5aa22;
    border-radius: 18px 18px 18px 4px; color: #d0f0e8;
  }}
  .ai-avatar {{
    width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0;
    background: linear-gradient(135deg, #00e5aa, #0088ff);
    display: flex; align-items: center; justify-content: center; font-size: 12px;
  }}

  /* Streaming text cursor */
  .streaming::after {{
    content: '▋'; animation: blink 0.7s infinite; color: #00e5aa; margin-left: 2px;
  }}
  @keyframes blink {{ 0%,100% {{ opacity:1 }} 50% {{ opacity:0 }} }}

  /* ── Bottom bar ── */
  #bottom {{
    position: fixed; bottom: 0; left: 0; right: 0;
    background: #09090f; border-top: 1px solid #151525;
    padding: 12px 16px 16px; z-index: 100;
  }}

  /* Text input row */
  #textRow {{
    display: flex; gap: 8px; margin-bottom: 10px;
  }}
  #textInput {{
    flex: 1; background: #0e0e1e; border: 1px solid #1e1e35;
    border-radius: 50px; color: #e0e0f0; font-size: 0.9rem;
    padding: 10px 18px; outline: none; font-family: 'DM Sans', sans-serif;
  }}
  #textInput:focus {{ border-color: #00e5aa44; }}
  #textInput::placeholder {{ color: #2a2a44; }}
  #sendBtn {{
    background: #00e5aa18; border: 1px solid #00e5aa44; color: #00e5aa;
    border-radius: 50px; padding: 10px 18px; cursor: pointer;
    font-family: 'Syne', sans-serif; font-size: 0.78rem; font-weight: 600;
    transition: all 0.15s;
  }}
  #sendBtn:hover {{ background: #00e5aa28; }}

  /* Mic button row */
  #micRow {{ display: flex; align-items: center; justify-content: center; gap: 16px; }}

  #micBtn {{
    width: 58px; height: 58px; border-radius: 50%; border: none; cursor: pointer;
    font-size: 1.6rem; display: flex; align-items: center; justify-content: center;
    transition: all 0.2s; outline: none;
    background: #0e0e20; border: 2px solid #1e1e38;
  }}
  #micBtn.idle    {{ background: #0e0e20; border-color: #1e1e38; }}
  #micBtn.listening {{
    background: #001a10; border-color: #00e5aa;
    box-shadow: 0 0 0 5px #00e5aa15, 0 0 20px #00e5aa20;
    animation: glowPulse 1.5s ease-in-out infinite;
  }}
  #micBtn.thinking {{
    background: #180a28; border-color: #8844ff;
    animation: glowPurple 1s ease-in-out infinite;
  }}
  #micBtn.speaking {{
    background: #001520; border-color: #0088ff;
    animation: glowBlue 0.8s ease-in-out infinite;
  }}
  @keyframes glowPulse  {{ 0%,100% {{ box-shadow: 0 0 0 4px #00e5aa15 }} 50% {{ box-shadow: 0 0 0 10px #00e5aa08 }} }}
  @keyframes glowPurple {{ 0%,100% {{ box-shadow: 0 0 0 4px #8844ff18 }} 50% {{ box-shadow: 0 0 0 10px #8844ff08 }} }}
  @keyframes glowBlue   {{ 0%,100% {{ box-shadow: 0 0 0 4px #0088ff18 }} 50% {{ box-shadow: 0 0 0 10px #0088ff08 }} }}

  .status-text {{
    font-family: 'Syne', sans-serif; font-size: 0.72rem; font-weight: 600;
    letter-spacing: 2px; text-transform: uppercase; color: #333355; min-width: 140px; text-align: center;
  }}
  .status-text.listening {{ color: #00e5aa; }}
  .status-text.thinking  {{ color: #8844ff; }}
  .status-text.speaking  {{ color: #0088ff; }}

  /* Voice selector */
  #voiceSelect {{
    background: #0e0e1e; border: 1px solid #1e1e30; border-radius: 20px;
    color: #555577; font-size: 0.68rem; padding: 4px 10px; outline: none;
    font-family: 'Syne', sans-serif;
  }}

  /* Empty state */
  #emptyState {{
    flex: 1; display: flex; flex-direction: column; align-items: center;
    justify-content: center; padding: 60px 20px; color: #1a1a2e;
  }}
  .empty-icon {{ font-size: 3rem; margin-bottom: 12px; opacity: 0.3; }}
  .empty-label {{
    font-family: 'Syne', sans-serif; font-size: 0.75rem;
    letter-spacing: 2.5px; text-transform: uppercase;
  }}
</style>
</head>
<body>

<!-- Conversation -->
<div id="conversation">
  <div id="emptyState">
    <div class="empty-icon">🎙️</div>
    <div class="empty-label">click mic to start talking</div>
  </div>
</div>

<!-- Bottom bar -->
<div id="bottom">
  <div id="textRow">
    <input id="textInput" type="text" placeholder="Or type a message...">
    <button id="sendBtn">Send</button>
  </div>
  <div id="micRow">
    <select id="voiceSelect" title="TTS voice"></select>
    <button id="micBtn" class="idle" title="Click to talk">🎙️</button>
    <div class="status-text" id="statusText">CLICK MIC</div>
  </div>
</div>

<script>
const BACKEND   = "http://localhost:8000";
const THREAD_ID = "{st.session_state.thread_id}";

// ── State ──────────────────────────────────────────────────────────────────
let state         = 'idle';   // idle | listening | thinking | speaking
let recognition   = null;
let synth         = window.speechSynthesis;
let voices        = [];
let currentUtter  = null;
let isListening   = false;

const micBtn     = document.getElementById('micBtn');
const statusText = document.getElementById('statusText');
const conv       = document.getElementById('conversation');
const emptyState = document.getElementById('emptyState');
const voiceSel   = document.getElementById('voiceSelect');
const textInput  = document.getElementById('textInput');
const sendBtn    = document.getElementById('sendBtn');

// ── Load TTS voices ────────────────────────────────────────────────────────
function loadVoices() {{
  voices = synth.getVoices().filter(v => v.lang.startsWith('en'));
  voiceSel.innerHTML = '';
  voices.forEach((v, i) => {{
    const opt = document.createElement('option');
    opt.value = i;
    opt.textContent = v.name.replace('Google ', '').replace('Microsoft ', '').substring(0, 22);
    // Prefer natural sounding voices
    if (v.name.includes('Neural') || v.name.includes('Natural') || v.name.includes('Aria') || v.name.includes('Guy')) {{
      opt.selected = true;
    }}
    voiceSel.appendChild(opt);
  }});
}}
loadVoices();
if (speechSynthesis.onvoiceschanged !== undefined) {{
  speechSynthesis.onvoiceschanged = loadVoices;
}}

// ── UI state machine ───────────────────────────────────────────────────────
function setState(s) {{
  state = s;
  micBtn.className = s;
  statusText.className = 'status-text ' + s;
  const labels = {{
    idle:      'CLICK MIC',
    listening: 'LISTENING...',
    thinking:  'THINKING...',
    speaking:  'SPEAKING...',
  }};
  statusText.textContent = labels[s] || s.toUpperCase();
  micBtn.textContent = s === 'listening' ? '⏹' : s === 'thinking' ? '⏳' : s === 'speaking' ? '🔊' : '🎙️';
}}

// ── Add message to UI ──────────────────────────────────────────────────────
function addMessage(role, text, streaming=false) {{
  if (emptyState) emptyState.style.display = 'none';

  const row = document.createElement('div');
  row.className = 'msg ' + role;

  if (role === 'ai') {{
    const avatar = document.createElement('div');
    avatar.className = 'ai-avatar';
    avatar.textContent = '🤖';
    row.appendChild(avatar);
  }}

  const bubble = document.createElement('div');
  bubble.className = 'bubble' + (streaming ? ' streaming' : '');
  bubble.textContent = text;
  row.appendChild(bubble);
  conv.appendChild(row);
  conv.scrollTop = conv.scrollHeight;
  return bubble;
}}

// ── Speak text using browser TTS ───────────────────────────────────────────
function speak(text, onDone) {{
  synth.cancel();
  currentUtter = new SpeechSynthesisUtterance(text);
  currentUtter.rate  = 1.05;
  currentUtter.pitch = 1.0;

  const idx = parseInt(voiceSel.value) || 0;
  if (voices[idx]) currentUtter.voice = voices[idx];

  currentUtter.onend = () => {{
    setState('idle');
    if (onDone) onDone();
  }};
  currentUtter.onerror = () => {{ setState('idle'); if (onDone) onDone(); }};

  setState('speaking');
  synth.speak(currentUtter);
}}

// ── Stream LLM response and speak sentence by sentence ────────────────────
async function streamAndSpeak(userText) {{
  setState('thinking');

  const bubble = addMessage('ai', '', true);
  let fullText  = '';
  let speakBuf  = '';
  let speakQueue = [];
  let isSpeaking = false;

  // Sentence boundary regex
  const sentenceEnd = /[.!?][\\s]/;

  function flushQueue() {{
    if (isSpeaking || speakQueue.length === 0) return;
    const sentence = speakQueue.shift();
    isSpeaking = true;
    setState('speaking');

    const utter = new SpeechSynthesisUtterance(sentence);
    utter.rate  = 1.05;
    utter.pitch = 1.0;
    const idx = parseInt(voiceSel.value) || 0;
    if (voices[idx]) utter.voice = voices[idx];

    utter.onend = () => {{
      isSpeaking = false;
      if (speakQueue.length > 0) {{
        flushQueue();
      }} else if (fullText && !streaming) {{
        setState('idle');
        // Auto-restart listening after speaking
        setTimeout(() => {{
          if (isListening) startListening();
        }}, 300);
      }}
    }};
    utter.onerror = () => {{ isSpeaking = false; flushQueue(); }};
    synth.speak(utter);
  }}

  let streaming = true;

  try {{
    const resp = await fetch(BACKEND + '/chat/stream', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ text: userText, thread_id: THREAD_ID }}),
    }});

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';

    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) break;

      buf += decoder.decode(value, {{ stream: true }});
      const lines = buf.split('\\n');
      buf = lines.pop();

      for (const line of lines) {{
        if (!line.startsWith('data: ')) continue;
        const chunk = line.slice(6);
        if (chunk === '[DONE]' || chunk.startsWith('[THREAD_ID:')) continue;

        const token = chunk.replace(/\\\\n/g, ' ');
        fullText  += token;
        speakBuf  += token;
        bubble.textContent = fullText;
        conv.scrollTop = conv.scrollHeight;

        // When we have a complete sentence, queue it for speaking
        if (sentenceEnd.test(speakBuf)) {{
          const parts = speakBuf.split(sentenceEnd);
          for (let i = 0; i < parts.length - 1; i++) {{
            const sentence = parts[i].trim();
            if (sentence) speakQueue.push(sentence + '.');
          }}
          speakBuf = parts[parts.length - 1];
          flushQueue();
        }}
      }}
    }}

    // Speak any remaining text
    if (speakBuf.trim()) speakQueue.push(speakBuf.trim());
    streaming = false;
    bubble.classList.remove('streaming');
    flushQueue();

    if (!isSpeaking && speakQueue.length === 0) {{
      setState('idle');
      setTimeout(() => {{ if (isListening) startListening(); }}, 300);
    }}

  }} catch(e) {{
    bubble.textContent = 'Error: ' + e.message;
    bubble.classList.remove('streaming');
    setState('idle');
  }}
}}

// ── Speech recognition ─────────────────────────────────────────────────────
function setupRecognition() {{
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {{
    statusText.textContent = 'BROWSER NOT SUPPORTED';
    micBtn.disabled = true;
    return null;
  }}

  const r = new SR();
  r.continuous      = false;
  r.interimResults  = true;
  r.lang            = 'en-US';
  r.maxAlternatives = 1;

  let interimBubble = null;
  let finalText     = '';

  r.onstart = () => {{
    setState('listening');
    finalText = '';
    interimBubble = addMessage('user', '...', false);
  }};

  r.onresult = (e) => {{
    let interim = '';
    finalText = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {{
      if (e.results[i].isFinal) {{
        finalText += e.results[i][0].transcript;
      }} else {{
        interim += e.results[i][0].transcript;
      }}
    }}
    if (interimBubble) interimBubble.textContent = finalText || interim || '...';
  }};

  r.onend = () => {{
    if (finalText.trim()) {{
      if (interimBubble) interimBubble.textContent = '🎙️ ' + finalText.trim();
      streamAndSpeak(finalText.trim());
    }} else {{
      // Nothing heard — remove placeholder and go back to idle
      if (interimBubble && interimBubble.closest('.msg')) {{
        interimBubble.closest('.msg').remove();
      }}
      setState('idle');
    }}
    interimBubble = null;
  }};

  r.onerror = (e) => {{
    console.error('SR error:', e.error);
    if (interimBubble && interimBubble.closest('.msg')) {{
      interimBubble.closest('.msg').remove();
    }}
    setState('idle');
  }};

  return r;
}}

// ── Start / stop listening ─────────────────────────────────────────────────
function startListening() {{
  if (state !== 'idle') return;
  synth.cancel();
  recognition = setupRecognition();
  if (recognition) recognition.start();
}}

function stopListening() {{
  if (recognition) {{ try {{ recognition.stop(); }} catch(e) {{}} }}
}}

// ── Mic button ─────────────────────────────────────────────────────────────
micBtn.addEventListener('click', () => {{
  if (state === 'idle') {{
    isListening = true;
    startListening();
  }} else if (state === 'listening') {{
    isListening = false;
    stopListening();
  }} else if (state === 'speaking') {{
    synth.cancel();
    setState('idle');
  }}
}});

// ── Text input ─────────────────────────────────────────────────────────────
function sendText() {{
  const text = textInput.value.trim();
  if (!text) return;
  textInput.value = '';
  addMessage('user', text);
  streamAndSpeak(text);
}}
sendBtn.addEventListener('click', sendText);
textInput.addEventListener('keydown', (e) => {{
  if (e.key === 'Enter') sendText();
}});
</script>
</body>
</html>
"""

components.html(VOICE_APP, height=700, scrolling=False)