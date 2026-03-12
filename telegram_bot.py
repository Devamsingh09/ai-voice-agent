"""
Telegram AI Bot — Text + Voice Input
──────────────────────────────────────
Text message  → Backend → AI response (text)
Voice message → Download OGG → Whisper STT → Backend → AI response (text)

Setup:
1. Talk to @BotFather → /newbot → copy token
2. Add TELEGRAM_BOT_TOKEN to .env
3. Run: python telegram_bot.py
"""

import os
import logging
import httpx
import tempfile
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

load_dotenv()

# ── Config ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
BACKEND_URL        = os.getenv("BACKEND_URL", "http://localhost:8000")

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────

def get_thread_id(user_id: int) -> str:
    """Each Telegram user gets their own conversation thread."""
    return f"tg_{user_id}"


def ask_backend_text(text: str, thread_id: str) -> str:
    """Send text to FastAPI backend, get AI response."""
    try:
        response = httpx.post(
            f"{BACKEND_URL}/voice/text",
            json={"text": text, "thread_id": thread_id},
            params={"return_audio": False},
            timeout=30,
        )
        if response.status_code == 200:
            ct = response.headers.get("content-type", "")
            if ct.startswith("audio"):
                return response.headers.get("x-ai-response", "Sorry, no response.")
            return response.json().get("ai_response", "Sorry, no response.")
        return f"Backend error: {response.status_code}"
    except httpx.ConnectError:
        return "❌ Backend offline. Run: uvicorn app.main:app --reload --port 8000"
    except Exception as e:
        return f"❌ Error: {str(e)}"


def ask_backend_voice(audio_path: str, thread_id: str) -> dict:
    """Send audio file to FastAPI backend → STT → LLM → response."""
    try:
        with open(audio_path, "rb") as f:
            response = httpx.post(
                f"{BACKEND_URL}/voice/input",
                files={"audio": (Path(audio_path).name, f, "audio/ogg")},
                data={"thread_id": thread_id, "return_audio": "false"},
                timeout=60,
            )
        if response.status_code == 200:
            ct = response.headers.get("content-type", "")
            if ct.startswith("audio"):
                return {
                    "transcribed": response.headers.get("x-transcribed-text", ""),
                    "response":    response.headers.get("x-ai-response", ""),
                }
            data = response.json()
            return {
                "transcribed": data.get("transcribed_text", ""),
                "response":    data.get("ai_response", ""),
            }
        return {"error": f"Backend error: {response.status_code}"}
    except httpx.ConnectError:
        return {"error": "❌ Backend offline."}
    except Exception as e:
        return {"error": f"❌ Error: {str(e)}"}


# ── Command Handlers ───────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"👋 Hey {user.first_name}!\n\n"
        f"I'm an AI Voice Agent powered by LLaMA 3.1.\n\n"
        f"You can:\n"
        f"💬 Send a *text message* — I'll reply\n"
        f"🎙️ Send a *voice message* — I'll transcribe + reply\n\n"
        f"Commands:\n"
        f"/start — Show this message\n"
        f"/clear — Clear conversation history\n"
        f"/help  — Help",
        parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *AI Voice Agent Bot*\n\n"
        "💬 *Text:* Just type anything\n"
        "🎙️ *Voice:* Send a voice message — I'll understand it\n\n"
        "I remember your conversation — use /clear to start fresh.",
        parse_mode="Markdown"
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = get_thread_id(update.effective_user.id)
    try:
        httpx.delete(f"{BACKEND_URL}/history/{thread_id}", timeout=5)
        await update.message.reply_text("🗑️ Conversation cleared! Starting fresh.")
    except Exception:
        await update.message.reply_text("⚠️ Could not clear history.")


# ── Message Handlers ───────────────────────────────────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages."""
    user      = update.effective_user
    user_text = update.message.text
    thread_id = get_thread_id(user.id)

    logger.info(f"[TEXT] User {user.id}: {user_text[:60]}")

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    ai_response = ask_backend_text(user_text, thread_id)
    logger.info(f"[TEXT] Response: {ai_response[:60]}")
    await update.message.reply_text(ai_response)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle voice messages.
    Flow: Download OGG from Telegram → send to /voice/input → Whisper STT → LLM → reply
    """
    user      = update.effective_user
    thread_id = get_thread_id(user.id)

    logger.info(f"[VOICE] User {user.id} sent voice message")

    # Show typing indicator
    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action="typing"
    )

    # Download voice file from Telegram
    voice_file = await context.bot.get_file(update.message.voice.file_id)

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "voice.ogg")
        await voice_file.download_to_drive(audio_path)
        logger.info(f"[VOICE] Downloaded to {audio_path}")

        # Send to backend → STT → LLM
        result = ask_backend_voice(audio_path, thread_id)

    if "error" in result:
        await update.message.reply_text(result["error"])
        return

    transcribed = result.get("transcribed", "")
    ai_response = result.get("response", "")

    logger.info(f"[VOICE] Transcribed: {transcribed[:60]}")
    logger.info(f"[VOICE] Response: {ai_response[:60]}")

    # Reply with transcription + AI response
    reply = ""
    if transcribed:
        reply += f"🎙️ *You said:* _{transcribed}_\n\n"
    reply += f"🤖 {ai_response}"

    await update.message.reply_text(reply, parse_mode="Markdown")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not set in .env")
        print("   1. Talk to @BotFather on Telegram")
        print("   2. /newbot → follow steps → copy token")
        print("   3. Add to .env: TELEGRAM_BOT_TOKEN=your_token_here")
        return

    print(f"🤖 Starting Telegram bot...")
    print(f"🔗 Backend: {BACKEND_URL}")

    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()

    # Register handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help",  help_command))
    app.add_handler(CommandHandler("clear", clear))

    # Text messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Voice messages  ← NEW
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    app.add_error_handler(error_handler)

    print("✅ Bot running! Supports text + voice messages.")
    print("   Open Telegram → search your bot → send text or voice")

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()