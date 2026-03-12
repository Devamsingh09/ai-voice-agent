import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")
    DB_PATH: str = os.getenv("DB_PATH", "./data/memory.db")
    APP_HOST: str = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT: int = int(os.getenv("APP_PORT", "8000"))


settings = Settings()
