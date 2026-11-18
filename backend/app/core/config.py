from functools import lru_cache
from pathlib import Path
import os

from dotenv import load_dotenv
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = BACKEND_ROOT / ".env"
load_dotenv(str(ENV_FILE))

class Settings(BaseSettings):
    APP_NAME:str="AI System"
    # --- Database ---
    # ONE source of truth: these same POSTGRES_* values are read by docker-compose
    # (env_file: backend/.env) to create the database, and used here to build the
    # connection URLs, so the password is written exactly once.
    POSTGRES_USER: str = "ai_user"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "ai_agent_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5433  # docker-compose maps the container's 5432 to 5433
    # Optional full overrides (e.g. a hosted database); built from the parts if empty.
    DATABASE_URL_ASYNC: str | None = None
    DATABASE_URL_SYNC: str | None = None
    ENV:str="dev"
    DB_ECHO: bool = False  # True prints every SQL statement (debugging only)
    # --- Auth ---
    # Required, no default: the app must not start with a guessable signing key.
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_MINUTES: int = 60
    # Refresh tokens: long-lived, rotated on every use, revocable (stored hashed).
    REFRESH_TOKEN_DAYS: int = 7
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
    # Eval judge: a DIFFERENT model family than the agents (limits self-preference bias).
    EVAL_JUDGE_MODEL: str = "openai/gpt-oss-20b"
    # Used when the main judge is out of quota for longer than a short wait (e.g. the
    # free tier's tokens-per-day). Groq budgets are per model; NOT a Gemini model,
    # because the answers being judged come from Gemini agents (self-preference bias).
    EVAL_JUDGE_FALLBACK_MODEL: str = "openai/gpt-oss-120b"
    GROQ_API_KEY: str | None = None
    GEMINI_API_KEY: str | None = None
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_WORKERS: int = 4
    MAINTENANCE_LLM_MAX_WORKERS: int = 1
    # Background memory maintenance holds a DB session across slow LLM calls. Cap how
    # many run at once so they can never take the whole pool from user requests.
    MAINTENANCE_MAX_CONCURRENT_RUNS: int = 2
    # Explicit pool: fail in 10s instead of hanging 30s when starved; drop dead connections.
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: int = 10
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
    # Every Gemini HTTP call (embeddings, OCR, image analysis). The SDK default is
    # NO timeout: a dropped connection used to hang an upload in "processing" forever.
    GEMINI_HTTP_TIMEOUT_MS: int = 60_000
    # RAG over uploaded files: "hybrid" (keyword + vector, fused) or "vector" (vector only).
    RETRIEVAL_MODE: str = "hybrid"
    MEMORY_MAX_DISTANCE: float = 0.9
    RELATED_CONVERSATION_MAX_DISTANCE: float = 0.85
    FILE_PROCESSING_BACKEND: str = "local"
    CELERY_BROKER_URL: str | None = None
    CELERY_RESULT_BACKEND: str | None = None

    @model_validator(mode="after")
    def _build_database_urls(self):
        def url(driver: str) -> str:
            # URL.create escapes special characters in the password (e.g. "@", "/"),
            # which naive f-string formatting would break.
            return URL.create(
                drivername=driver,
                username=self.POSTGRES_USER,
                password=self.POSTGRES_PASSWORD,
                host=self.POSTGRES_HOST,
                port=self.POSTGRES_PORT,
                database=self.POSTGRES_DB,
            ).render_as_string(hide_password=False)

        self.DATABASE_URL_ASYNC = self.DATABASE_URL_ASYNC or url("postgresql+asyncpg")
        self.DATABASE_URL_SYNC = self.DATABASE_URL_SYNC or url("postgresql+psycopg2")
        return self

    model_config = SettingsConfigDict(env_file=str(ENV_FILE), extra="ignore")

@lru_cache
def get_settings():
    return Settings()

settings=get_settings()
