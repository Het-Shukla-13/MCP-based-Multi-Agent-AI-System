"""External HTTP clients must have timeouts: a dropped connection otherwise hangs forever."""
import ast
from pathlib import Path


def test_every_gemini_client_sets_an_http_timeout():
    app = Path(__file__).parents[1] / "app"
    missing = []
    for path in app.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "Client" and getattr(node.func.value, "id", "") == "genai"
                    and not any(k.arg == "http_options" for k in node.keywords)):
                missing.append(f"{path.relative_to(app)}:{node.lineno}")
    assert missing == [], f"genai.Client without http_options timeout: {missing}"


def test_embedding_fails_fast_when_the_provider_asks_for_a_long_wait(monkeypatch):
    import pytest

    from app.services.embeddings import embedding_utils as eu

    class Daily(Exception):
        def __str__(self):
            return "429 RESOURCE_EXHAUSTED {'retryDelay': '78760s'}"

    class FakeModels:
        def embed_content(self, **_):
            raise Daily()

    monkeypatch.setattr(eu, "_get_client", lambda: type("C", (), {"models": FakeModels()})())
    monkeypatch.setattr(eu._limiter, "acquire", lambda n: None)
    slept = []
    monkeypatch.setattr(eu.time, "sleep", lambda s: slept.append(s))
    with pytest.raises(eu.EmbeddingQuotaExhausted, match="21.9 h"):
        eu._embed_batch(["x"], "document")
    assert slept == []  # never went to sleep for 22 hours
