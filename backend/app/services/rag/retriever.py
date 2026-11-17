"""
Retrieval over the user's uploaded files: hybrid search over child chunks,
answered with their parent passages.

1. Candidates, two ways (children only):
   - vector: cosine distance on the HNSW index (meaning, paraphrases);
   - keyword: Postgres full-text search on chunk.search_vector (exact terms:
     codes like HX-3127-C, names, numbers) - RETRIEVAL_MODE="hybrid" only.
2. Reciprocal Rank Fusion: score = sum(1 / (RRF_K + rank)) over both lists.
   Ranks, not raw scores, so a cosine 0.71 and a ts_rank 0.05 never need to be
   put on one scale.
3. Map each child to its parent passage (or itself), de-duplicate, and stop at
   TOP_K_PASSAGES or the character budget. The agent reads parents.

The old "section scoping" step (keep only the best-scoring section) was removed:
on the retrieval eval it dropped correct chunks (e.g. a title-word match on
"Shifts (Leipzig)" beat the right "Emergency procedures (Leipzig)" chunk).
"""

from __future__ import annotations

import re
from typing import Any

from loguru import logger
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.config import settings
from app.models.chunks import Chunk, ChunkParent
from app.models.file import File
from app.services.embeddings.embedding_utils import embed_text_async
from app.services.time.timing import log_async_timing



CANDIDATES_PER_METHOD = 30
TOP_K_PASSAGES = 4
CONTEXT_BUDGET_CHARS = 6000
RRF_K = 60
KEYWORD_WEIGHT_IDENTIFIER = 1.0
KEYWORD_WEIGHT_PLAIN = 0.3
_TERM = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.\-]*[A-Za-z0-9]|[A-Za-z0-9]")


def _section_key(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    for key in ("section_id", "sheet", "filename"):
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return f"{key}:{value}"
    return f"chunk:{chunk.get('id')}"


def _section_label(chunk: dict[str, Any]) -> str:
    metadata = chunk.get("metadata") or {}
    for key in ("section_title", "sheet", "filename", "type"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _owned_chunks(file_ids, conversation_id, user_id):
    return (
        select(
            Chunk.id.label("id"),
            Chunk.content.label("content"),
            Chunk.file_metadata.label("metadata"),
            Chunk.parent_id.label("parent_id"),
            File.filename.label("filename"),
        )
        .join(File, File.id == Chunk.file_id)
        .where(
            Chunk.file_id.in_(file_ids),
            File.conversation_id == conversation_id,
            File.user_id == user_id,
            File.status == "processed",
        )
    )


async def _vector_candidates(query_embedding, file_ids, conversation_id, user_id, db, limit):
    # HNSW + a WHERE filter: by default the index returns ~ef_search nearest rows
    # of ALL users and the filter runs afterwards, which can leave too few rows.
    # pgvector >= 0.8 iterative scans keep walking the index until LIMIT is met.
    await db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    query = (
        _owned_chunks(file_ids, conversation_id, user_id)
        # cosine_distance matches the HNSW index (vector_cosine_ops) on chunk.embedding.
        .order_by(Chunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return [dict(row) for row in (await db.execute(query)).mappings().all()]


def keyword_weight(query_text: str) -> float:
    """
    Keyword search shines on rare identifiers (HX-3127-C, E-7731, DC-09) and adds
    noise on plain questions, where words like a city name match many sections
    equally. Measured on the retrieval eval: full weight only when the query
    contains a term with a digit.
    """
    return KEYWORD_WEIGHT_IDENTIFIER if any(any(ch.isdigit() for ch in term) for term in keyword_terms(query_text)) \
        else KEYWORD_WEIGHT_PLAIN


def keyword_terms(query_text: str) -> list[str]:
    return list(dict.fromkeys(_TERM.findall(query_text or "")))[:32]


async def _keyword_candidates(query_text, file_ids, conversation_id, user_id, db, limit):
    terms = keyword_terms(query_text)
    if not terms:
        return []
    # OR of the query's terms (stop words drop out; plainto_tsquery keeps
    # "HX-3127-C" as one phrase). websearch_to_tsquery would AND every word,
    # which a natural-language question almost never satisfies.
    tsquery = None
    for term in terms:
        part = func.plainto_tsquery("english", term)
        tsquery = part if tsquery is None else tsquery.op("||")(part)
    rank = func.ts_rank_cd(Chunk.search_vector, tsquery)
    query = (
        _owned_chunks(file_ids, conversation_id, user_id)
        .where(Chunk.search_vector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(limit)
    )
    return [dict(row) for row in (await db.execute(query)).mappings().all()]


def reciprocal_rank_fusion(*ranked_lists: list[dict], weights: tuple[float, ...] | None = None,
                           k: int = RRF_K) -> list[dict]:
    scores: dict[Any, float] = {}
    rows: dict[Any, dict] = {}
    for index, ranked in enumerate(ranked_lists):
        weight = weights[index] if weights else 1.0
        for rank, row in enumerate(ranked, start=1):
            scores[row["id"]] = scores.get(row["id"], 0.0) + weight / (k + rank)
            rows.setdefault(row["id"], row)
    return [rows[i] for i in sorted(scores, key=scores.get, reverse=True)]


async def _to_passages(ranked_chunks: list[dict], db, top_k: int, budget: int) -> list[dict]:
    """Best children -> their parents, de-duplicated, within top_k and the budget."""
    parent_ids = {c["parent_id"] for c in ranked_chunks if c.get("parent_id")}
    parents = {}
    if parent_ids:
        result = await db.execute(select(ChunkParent.id, ChunkParent.content).where(ChunkParent.id.in_(parent_ids)))
        parents = {row.id: row.content for row in result}
    passages, seen, used = [], set(), 0
    for chunk in ranked_chunks:
        key = chunk.get("parent_id") or chunk["id"]
        if key in seen:
            continue
        content = parents.get(chunk.get("parent_id")) or chunk["content"]
        if passages and used + len(content) > budget:
            continue  # a smaller passage further down may still fit
        seen.add(key)
        used += len(content)
        passages.append({**chunk, "content": content})
        if len(passages) >= top_k:
            break
    return passages


async def retrieve_similar_chunks(
    query_text: str,
    query_embedding,
    file_ids,
    conversation_id,
    user_id,
    db: AsyncSession,
    top_k: int = TOP_K_PASSAGES,
    budget: int = CONTEXT_BUDGET_CHARS,
):
    if not file_ids:
        return []
    if query_embedding is None:
        # Embeddings unavailable (quota/outage): keyword search needs no external
        # API, so file questions still get an answer instead of a failed turn.
        keyword = await _keyword_candidates(query_text, file_ids, conversation_id, user_id, db, CANDIDATES_PER_METHOD)
        return await _to_passages(keyword, db, top_k, budget)
    ranked = await _vector_candidates(query_embedding, file_ids, conversation_id, user_id, db, CANDIDATES_PER_METHOD)
    if settings.RETRIEVAL_MODE == "hybrid":
        keyword = await _keyword_candidates(query_text, file_ids, conversation_id, user_id, db, CANDIDATES_PER_METHOD)
        ranked = reciprocal_rank_fusion(ranked, keyword, weights=(1.0, keyword_weight(query_text)))
    return await _to_passages(ranked, db, top_k, budget)


def build_context(chunks):
    """Passages with a "Source: file > section" line (lets the agent cite where it read it)."""
    blocks: list[str] = []
    for chunk in chunks:
        content = (chunk.get("content") or "").strip()
        if not content:
            continue
        source = " > ".join(x for x in (chunk.get("filename"), _section_label(chunk)) if x)
        blocks.append(f"Source: {source}\n{content}" if source else content)
    return "\n\n---\n\n".join(blocks)

async def get_processed_file_ids(
    conversation_id,
    user_id,
    db: AsyncSession,
    limit: int = 12,
    file_ids: list | None = None,
):
    query = (
        select(File.id)
        .where(
            File.conversation_id == conversation_id,
            File.user_id == user_id,
            File.status == "processed",
        )
        .order_by(File.created_at.desc())
        .limit(limit)
    )
    if file_ids:
        query = query.where(File.id.in_(file_ids))

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_pending_file_names(
    conversation_id,
    user_id,
    db: AsyncSession,
    file_ids: list | None = None,
):
    if not file_ids:
        return []

    result = await db.execute(
        select(File.filename)
        .where(
            File.id.in_(file_ids),
            File.conversation_id == conversation_id,
            File.user_id == user_id,
            File.status != "processed",
        )
        .order_by(File.created_at.desc())
    )
    return list(result.scalars().all())

@log_async_timing("retrieve_pipeline")
async def retrieve_pipeline(
    query: str,
    file_ids,
    conversation_id,
    user_id,
    db: AsyncSession,
):
    prioritized_file_ids = await get_processed_file_ids(
        conversation_id,
        user_id,
        db,
        file_ids=file_ids,
    )
    if prioritized_file_ids:
        searchable_file_ids = prioritized_file_ids
    else:
        searchable_file_ids = await get_processed_file_ids(
            conversation_id,
            user_id,
            db,
        )

    pending_file_names = await get_pending_file_names(
        conversation_id,
        user_id,
        db,
        file_ids=file_ids,
    )

    if not searchable_file_ids:
        if pending_file_names:
            pending_files = "\n".join(f"- {name}" for name in pending_file_names)
            return (
                "Attached files are still being processed and are not searchable yet:\n"
                f"{pending_files}"
            )
        return ""

    try:
        user_query = await embed_text_async(query, task="query")
    except Exception as exc:
        logger.warning("Query embedding failed; keyword-only retrieval | error={}", str(exc)[:200])
        user_query = None
    similar_chunks = await retrieve_similar_chunks(
        query,
        user_query,
        searchable_file_ids,
        conversation_id,
        user_id,
        db,
    )
    context = build_context(similar_chunks)
    if pending_file_names:
        pending_files = "\n".join(f"- {name}" for name in pending_file_names)
        pending_notice = (
            "Attached files still processing and not yet included in retrieval:\n"
            f"{pending_files}"
        )
        return f"{pending_notice}\n\n---\n\n{context}" if context else pending_notice
    return context
