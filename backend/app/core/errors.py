"""Exception -> HTTP response mapping for errors that aren't the client's fault."""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.services.embeddings.embedding_utils import EmbeddingQuotaExhausted

QUOTA_MESSAGE = (
    "Memory and file search are temporarily unavailable: the AI provider's daily "
    "quota has been reached. Chat still works; please try this again later."
)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(EmbeddingQuotaExhausted)
    async def quota_exhausted(request: Request, exc: EmbeddingQuotaExhausted) -> JSONResponse:
        # 503 + Retry-After: a temporary server-side condition, not a bug (500) and
        # not the client's fault (4xx). Clients and proxies know to retry later.
        logger.warning("Quota exhausted | {} {} | {}", request.method, request.url.path, exc)
        headers = {"Retry-After": str(int(exc.retry_after_seconds))} if exc.retry_after_seconds else {}
        return JSONResponse(status_code=503, content={"detail": QUOTA_MESSAGE}, headers=headers)
