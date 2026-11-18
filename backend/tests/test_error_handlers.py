"""Quota exhaustion is a temporary server condition: 503 + Retry-After, not a 500."""
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import QUOTA_MESSAGE, register_error_handlers
from app.services.embeddings.embedding_utils import EmbeddingQuotaExhausted


def make_app() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/memories")
    async def create_memory():
        raise EmbeddingQuotaExhausted("quota", retry_after_seconds=5760.4)

    @app.get("/search")
    async def search():
        raise EmbeddingQuotaExhausted("quota")

    return TestClient(app)


def test_quota_exhausted_is_503_with_retry_after():
    response = make_app().post("/memories")
    assert response.status_code == 503
    assert response.json() == {"detail": QUOTA_MESSAGE}
    assert response.headers["Retry-After"] == "5760"


def test_retry_after_omitted_when_unknown():
    response = make_app().get("/search")
    assert response.status_code == 503 and "Retry-After" not in response.headers
