"""
Search a user's conversations by what was said in them (and by title).

Postgres full-text search over message.content, backed by the GIN expression
index message_content_fts_idx (migration "message content search index").

- websearch_to_tsquery: plain words are AND-ed (what people expect from a search
  box), "quoted phrases" and -exclusions work, and it never raises on odd input.
- One result per conversation (its best-matching message), plus conversations
  whose TITLE contains the text (substring, so it also works while typing).
- Highlights are marked with control characters (HL_START / HL_END), never HTML,
  so the client can render them without innerHTML.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

HL_START, HL_END = "\x01", "\x02"
MIN_QUERY_CHARS = 2
MAX_RESULTS = 20

_CONTENT_SQL = text(f"""
WITH q AS (SELECT websearch_to_tsquery('english', :q) AS query),
hits AS (
    SELECT DISTINCT ON (m.conversation_id)
           m.conversation_id, m.id AS message_id, m.role, m.created_at,
           ts_rank(to_tsvector('english', m.content), q.query) AS rank,
           ts_headline('english', m.content, q.query,
                       'StartSel={HL_START}, StopSel={HL_END}, MaxWords=24, MinWords=8, MaxFragments=1') AS snippet
    FROM message m
    JOIN conversation c ON c.id = m.conversation_id, q
    WHERE c.user_id = :user_id
      AND to_tsvector('english', m.content) @@ q.query
    ORDER BY m.conversation_id, rank DESC, m.created_at DESC
)
SELECT hits.*, c.title, c.updated_at
FROM hits JOIN conversation c ON c.id = hits.conversation_id
ORDER BY hits.rank DESC, hits.created_at DESC
LIMIT :limit
""")

_TITLE_SQL = text("""
SELECT c.id AS conversation_id, c.title, c.updated_at
FROM conversation c
WHERE c.user_id = :user_id AND c.title ILIKE :pattern ESCAPE '\\'
ORDER BY c.updated_at DESC
LIMIT :limit
""")


def _like_pattern(query: str) -> str:
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def search_conversations(db: AsyncSession, user_id, query: str, limit: int = MAX_RESULTS) -> list[dict]:
    query = (query or "").strip()[:200]
    if len(query) < MIN_QUERY_CHARS:
        return []
    params = {"user_id": user_id, "limit": limit}
    content_rows = (await db.execute(_CONTENT_SQL, {**params, "q": query})).mappings().all()
    title_rows = (await db.execute(_TITLE_SQL, {**params, "pattern": _like_pattern(query)})).mappings().all()

    results: dict = {}
    for row in title_rows:  # title matches first: the most direct hit
        results[row["conversation_id"]] = {
            "conversation_id": str(row["conversation_id"]), "title": row["title"], "match": "title",
            "message_id": None, "role": None, "snippet": None, "updated_at": row["updated_at"],
        }
    for row in content_rows:
        entry = results.setdefault(row["conversation_id"], {
            "conversation_id": str(row["conversation_id"]), "title": row["title"], "match": "message",
            "updated_at": row["updated_at"],
        })
        entry.update(message_id=str(row["message_id"]), role=row["role"], snippet=row["snippet"])
    return list(results.values())[:limit]
