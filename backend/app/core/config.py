from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"
load_dotenv(str(ENV_FILE))

class Settings(BaseSettings):
    APP_NAME:str="AI System"
    DATABASE_URL_ASYNC: str
    DATABASE_URL_SYNC: str
    ENV:str="dev"
    DB_ECHO: bool = False  # True prints every SQL statement (debugging only)
    # Browser origins allowed to call the API (JSON list in .env).
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]
    # --- LLM models (free tiers only; verify availability before changing) ---
    # Non-agent LLM calls (routing, summarization, memory, metadata, file generation).
    # Names starting with "gemini" go to Google AI Studio; anything else goes to Groq.
    MODEL: str = "openai/gpt-oss-20b"
    CHAT_MODEL: str | None = None          # overrides MODEL for foreground calls
    MAINTENANCE_MODEL: str | None = None   # overrides MODEL for background memory calls
    LLM_FALLBACK_MODEL: str | None = "gemini-3.5-flash-lite"  # used when the primary is rate-limited/unavailable
    # gpt-oss is a reasoning model: "low" keeps latency/tokens small for our short tasks.
    LLM_REASONING_EFFORT: str = "low"
    # ADK agents (Gemini via google-adk).
    AGENT_MODEL: str = "gemini-3.1-flash-lite"
    AGENT_FALLBACK_MODEL: str | None = "gemini-3.5-flash-lite"
    # Root agent (routing only). A different model than the agents spreads the
    # free-tier per-model quota: one chat turn = 1 router call + 1 agent call.
    ROUTER_MODEL: str = "gemini-3.5-flash-lite"
    ROUTER_FALLBACK_MODEL: str | None = "gemini-3.1-flash-lite"
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_WORKERS: int = 4
    MAINTENANCE_LLM_MAX_WORKERS: int = 1
    MAINTENANCE_MAX_COMPARISONS_PER_RUN: int = 6
    MAINTENANCE_MIN_COMPARISONS_FOR_OPTIONAL_STAGES: int = 1
    MAINTENANCE_MIN_COMPARISONS_FOR_PROFILE_REFRESH: int = 1
    PROFILE_MAX_LLM_COMPARISONS_PER_REFRESH: int = 3
    # Stream reply text to the browser as it is generated (WebSocket chat_delta events).
    STREAMING_ENABLED: bool = True
    # --- Embeddings (Gemini, free tier: 100 requests/min; each text = 1 request) ---
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIM: int = 768  # changing this requires a migration + scripts/reembed.py
    EMBEDDING_REQUESTS_PER_MINUTE: int = 90  # client-side limiter, headroom under 100
    # --- Memory relevance (L2 distance on normalized embeddings: 0 = identical, 2 = opposite) ---
    # Calibrated for gemini-embedding-001 query->document pairs: matches 0.60-0.77,
    # related 0.75-0.80, unrelated ~1.0. Recalibrate whenever the embedding model changes.
    MEMORY_MAX_DISTANCE: float = 0.9
    RELATED_CONVERSATION_MAX_DISTANCE: float = 0.85
    FILE_PROCESSING_BACKEND: str = "local"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

@lru_cache
def get_settings():
    return Settings()

settings=get_settings()
