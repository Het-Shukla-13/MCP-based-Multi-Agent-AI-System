# 04 · Memory pipeline crashes (`fix/memory-pipeline-crashes`)

## Bug 1: a Pydantic object treated as a dict
`compare_memories()` returns a `MemoryComparisonResult` (Pydantic). The dedup step in `ltm_service._check_duplicate_candidates` called `comparison.get("relationship")`. Pydantic models have no `.get`, so any near-duplicate memory raised `AttributeError` and killed that turn's background memory run. The conflict step 50 lines below already did `.model_dump()` first, so the codebase was inconsistent.

**Fix:** `comparison = comparison.model_dump()` before reading it. The function's contract is "returns a dict" (its exact-match branch builds a dict), so we convert at the boundary.

**Lesson:** decide on one shape per boundary, either model or dict, and convert in one place. Type hints such as `-> tuple[Memory | None, dict | None, ...]` describe that contract. A type checker (mypy/pyright) would have caught this.

## Bug 2: a function lying about its return type
`extract_conversation_metadata()` is annotated `-> ConversationMetadata`, but for empty text it returned a **dict**. The pipeline then called `.model_dump()` on it, which crashed. **Fix:** return `ConversationMetadata()`. Its fields already default to empty, which is why the model exists.

## Bug 3: silent failures
Six LLM helpers (memory extraction, annotation, comparison, profile extraction, metadata, context router) did `except Exception: return <default>` with **no log**. When Groq retired the model, every one of them failed silently and the app simply "had no memories". Nobody could see why.

**Fix:** keep the safe default, because background jobs must never break chat, but call `logger.exception(...)`, which logs the message **and the full traceback**.

**Rule:** never swallow an exception silently. Either handle it meaningfully, re-raise it, or at minimum log it with the traceback.

## Cleanup
Removed `from click import prompt` (a CLI library, almost certainly an IDE auto-import accident) from two files, plus unused `json`, `Any` and `fastapi_pagination.response` imports.

## Verified live
- Near-duplicate preferences → `duplicate`, 0.95 confidence, no crash ✅
- Unrelated memory → no match ✅
- Empty text → `ConversationMetadata` object ✅
- Real conversation → topics `['FastAPI','migrations','pgvector']` ✅
