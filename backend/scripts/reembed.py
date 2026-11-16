"""
Re-embed every chunk and memory whose embedding is NULL, with the current
EMBEDDING_MODEL. Run after changing the embedding model/dimension:

    .venv/bin/python -m scripts.reembed

Paced by the embedding rate limiter (free tier: ~90 texts/minute), so large
datasets take a while; it is safe to stop and re-run (only NULLs are processed).
"""

from sqlmodel import select

from app.db.database import sync_session_scope
from app.models import Memory
from app.models.chunks import Chunk
from app.services.embeddings.embedding_utils import embed_texts

BATCH = 50


def _reembed(model, label: str) -> int:
    done = 0
    while True:
        with sync_session_scope() as db:
            rows = db.exec(select(model).where(model.embedding.is_(None)).limit(BATCH)).all()
            if not rows:
                return done
            vectors = embed_texts([row.content for row in rows], task="document")
            for row, vector in zip(rows, vectors):
                row.embedding = vector
                db.add(row)
            db.commit()
            done += len(rows)
            print(f"{label}: {done} re-embedded", flush=True)


if __name__ == "__main__":
    print(f"chunks done: {_reembed(Chunk, 'chunks')}")
    print(f"memories done: {_reembed(Memory, 'memories')}")
