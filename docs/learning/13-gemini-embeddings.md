# 13 · Gemini embeddings + vision OCR, no local models (`feature/gemini-embeddings`)

## Why
- The spec says "Generate embeddings using Gemini".
- Project rule: no locally-run models. MiniLM pulled in PyTorch (~2 GB of dependencies); Tesseract is a local OCR model.
- Result: **venv 1.3 GB → 433 MB**, with no torch/transformers.

## Concept: vector spaces don't mix
Each embedding model has its own vector space. A MiniLM vector and a Gemini vector are **not comparable**, even if they had the same size. Switching models therefore requires:
1. **Schema:** `vector(384)` → `vector(768)`. The hand-written migration `1495dfd2a35e` drops the HNSW index, changes the type `USING NULL` (old vectors can't be converted), and recreates the index.
2. **Re-embedding:** `python -m scripts.reembed` refills every NULL embedding. It's idempotent (safe to stop and re-run).
3. **Recalibrating every distance threshold**, measured below.

## Measured free-tier limit
`embed_content_free_tier_requests: 100/minute`, and **each text in a batch counts as one request**. Our first 100-text test batch used the whole minute. So `embedding_utils.py` has:
- a thread-safe sliding-window **rate limiter** (90/min; ingestion waits instead of failing; a 300-chunk PDF takes ~3–4 min);
- **retry on 429** using the server's own `retryDelay`;
- an **LRU cache for query embeddings**: one chat turn searches files, memories and related conversations with the same question, now 1 API call instead of 3.

*Note:* the limiter is per process (app, Celery worker and MCP servers each have one), so the 429 retry is the backstop.

## Gemini embedding details
- **Asymmetric task types:** stored text uses `RETRIEVAL_DOCUMENT`, search questions use `RETRIEVAL_QUERY`. Gemini optimises each side for retrieval.
- **768 dimensions** via `output_dimensionality` (Matryoshka truncation of 3072). Truncated vectors are **not unit length**, so we L2-normalise them, because all thresholds assume normalised vectors.

## Recalibration (measured with gemini-embedding-001)
| Pair type | L2 distance |
|---|---|
| query → matching memory | 0.60–0.77 |
| query → related | 0.75–0.80 |
| query → unrelated | ~1.00 |
| memory ↔ paraphrase | 0.26–0.29 |
| memory ↔ contradiction ("lives in Ahmedabad" vs "Mumbai") | 0.37–0.41 |
| memory ↔ unrelated memory | ~0.64 |

| Setting | MiniLM value | Gemini value | Why |
|---|---|---|---|
| `MEMORY_MAX_DISTANCE` | 1.1 | **0.9** | 1.1 would let *every* unrelated memory through |
| `RELATED_CONVERSATION_MAX_DISTANCE` | 1.0 | **0.85** | |
| dedup gate (`DEDUP_DISTANCE_BY_TYPE`) | 0.14–0.20 | **0.30–0.35** | old values would miss every paraphrase |
| `FACT_CONFLICT_COMPARISON_MAX_DISTANCE` | 1.10 | **0.55** | catches contradictions, skips unrelated |

**Lesson:** thresholds belong to a *model*, not to the app. Recalibrate them with measured examples every time the embedding model changes.

## Memory refinement (update mechanism)
Live test: "I prefer Python over Java" then "Python is my favourite language" were 0.223 apart. The gate worked, but the comparator said *compatible (adds detail)*, so the old code stored a near-copy. Now *compatible + high confidence + more detail* inside the gate counts as a **refinement**: the existing memory is updated in place (new text + new embedding). Verified: one memory, with the richer wording.

## OCR → Gemini vision (`services/vision/vision_service.py`)
- Images are transcribed *and described* (charts, photos), so even images without text become searchable.
- `pymupdf4llm.to_markdown` silently ran Tesseract (`use_ocr=True` by default). Now `use_ocr=False`, and **scanned PDFs** (no text layer) are rendered to PNG and transcribed with vision, capped at 10 pages.

## Removed dependencies
`sentence-transformers`, `langchain-huggingface` (and with them torch/transformers), `pytesseract`, `pillow`. The unused `PROFILE_*_SIMILARITY_THRESHOLD` settings and `update_forward_refs` (deprecated) were also cleaned up.

## Verified live
- Ingestion → 768-d chunks.
- Image chunk text = the magazine page.
- "Who wrote the article in the image?" → Neil J. Rubenking.
- Memory dedup/refinement → 1 memory.

Tests: 26 passed.
