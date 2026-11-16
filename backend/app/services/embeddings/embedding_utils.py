"""
Embeddings via Gemini (gemini-embedding-001), the assignment requirement, with no
local model.

Key facts (measured on the free tier):
- 100 embed requests / minute / model, and EVERY text in a batch counts as one
  request. So a client-side rate limiter paces bulk work (file ingestion) instead of
  failing, and 429s are retried after the server's own retryDelay.
- Asymmetric task types: documents are embedded with RETRIEVAL_DOCUMENT, search
  queries with RETRIEVAL_QUERY. Gemini optimises the two sides differently,
  which improves retrieval.
- output_dimensionality=768 (Matryoshka truncation of the 3072-dim vector). Truncated
  vectors are NOT unit length, so we L2-normalise them; distance thresholds assume
  normalised vectors.
- One chat turn embeds the same question for RAG, memory and related-conversation
  search: a small LRU cache makes that one API call.
"""

import asyncio
import re
import threading
import time
from collections import OrderedDict
from typing import Literal

import numpy as np
from google import genai
from google.genai import types
from loguru import logger

from app.core.config import settings

EmbedTask = Literal["document", "query"]
_TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "RETRIEVAL_QUERY"}
MAX_BATCH = 50          # texts per API call (each still counts as one request)
MAX_RETRIES = 5
QUERY_CACHE_SIZE = 256

_client: genai.Client | None = None
_client_lock = threading.Lock()


def _get_client() -> genai.Client:
    global _client
    with _client_lock:
        if _client is None:
            _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


class _RateLimiter:
    """Thread-safe sliding-window limiter: at most `limit` texts per 60 seconds."""

    def __init__(self, limit: int):
        self.limit = max(1, limit)
        self._stamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self, n: int) -> None:
        n = min(n, self.limit)
        while True:
            with self._lock:
                now = time.monotonic()
                self._stamps = [t for t in self._stamps if now - t < 60]
                if len(self._stamps) + n <= self.limit:
                    self._stamps.extend([now] * n)
                    return
                wait = 60 - (now - self._stamps[0]) + 0.05
            time.sleep(max(wait, 0.05))


_limiter = _RateLimiter(settings.EMBEDDING_REQUESTS_PER_MINUTE)
_query_cache: OrderedDict[str, list[float]] = OrderedDict()
_cache_lock = threading.Lock()


def _retry_delay(exc: Exception, attempt: int) -> float:
    match = re.search(r"retryDelay'?:\s*'?(\d+)", str(exc))
    return float(match.group(1)) + 1 if match else min(60, 5 * 2**attempt)


def _normalize(vectors: list[list[float]]) -> list[list[float]]:
    matrix = np.asarray(vectors, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).tolist()


def _embed_batch(texts: list[str], task: EmbedTask) -> list[list[float]]:
    config = types.EmbedContentConfig(
        task_type=_TASK_TYPES[task],
        output_dimensionality=settings.EMBEDDING_DIM,
    )
    for attempt in range(MAX_RETRIES):
        _limiter.acquire(len(texts))
        try:
            response = _get_client().models.embed_content(
                model=settings.EMBEDDING_MODEL, contents=texts, config=config
            )
            return _normalize([e.values for e in response.embeddings])
        except Exception as exc:
            text = str(exc)
            if ("429" in text or "RESOURCE_EXHAUSTED" in text or "503" in text) and attempt < MAX_RETRIES - 1:
                delay = _retry_delay(exc, attempt)
                logger.warning("Embedding rate-limited; retrying in {}s (attempt {})", delay, attempt + 1)
                time.sleep(delay)
                continue
            raise
    raise RuntimeError("unreachable")


def embed_texts(texts: list[str], task: EmbedTask = "document") -> list[list[float]]:
    """Embed many texts (blocking). Used by file ingestion in worker threads."""
    cleaned = [t if t and t.strip() else " " for t in texts]
    vectors: list[list[float]] = []
    for start in range(0, len(cleaned), MAX_BATCH):
        vectors.extend(_embed_batch(cleaned[start:start + MAX_BATCH], task))
    return vectors


def embed_text(text: str, task: EmbedTask = "document") -> list[float]:
    if task == "query":
        key = text.strip()
        with _cache_lock:
            if key in _query_cache:
                _query_cache.move_to_end(key)
                return _query_cache[key]
        vector = embed_texts([text], task)[0]
        with _cache_lock:
            _query_cache[key] = vector
            if len(_query_cache) > QUERY_CACHE_SIZE:
                _query_cache.popitem(last=False)
        return vector
    return embed_texts([text], task)[0]


async def embed_text_async(text: str, task: EmbedTask = "document") -> list[float]:
    """Non-blocking for the event loop (network call + possible rate-limit wait in a thread)."""
    return await asyncio.to_thread(embed_text, text, task)
