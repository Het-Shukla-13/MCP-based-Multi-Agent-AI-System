"""
Re-chunk documents uploaded before parent/child chunking (PDF, DOCX, MD, TXT):

    .venv/bin/python -m scripts.rechunk            # all users
    .venv/bin/python -m scripts.rechunk --dry-run  # just list what would change

A document qualifies when it is processed, still on disk and none of its chunks
has a parent. New chunks are stored first and the old ones deleted after, so a
failure never leaves a file without chunks. Safe to stop and re-run. Paced by
the embedding rate limiter (~90 chunks/minute on the free tier).
"""
import argparse
import os

from sqlalchemy import delete, exists, select

from app.db.database import sync_session_scope
from app.models.chunks import Chunk
from app.models.file import File
from app.services.file_processing.file_ingestion import ingest_file

DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".md", ".txt"}


def candidates() -> list[File]:
    with sync_session_scope() as db:
        has_parent = exists().where(Chunk.file_id == File.id, Chunk.parent_id.is_not(None))
        files = db.execute(select(File).where(File.status == "processed", ~has_parent)).scalars().all()
        return [f for f in files
                if os.path.splitext(f.filename)[1].lower() in DOCUMENT_EXTENSIONS and os.path.exists(f.storage_path)]


def rechunk(file: File) -> int:
    with sync_session_scope() as db:
        old_ids = list(db.execute(select(Chunk.id).where(Chunk.file_id == file.id)).scalars())
    count = ingest_file(str(file.id), file.storage_path)  # adds the new parent/child chunks
    with sync_session_scope() as db:
        db.execute(delete(Chunk).where(Chunk.id.in_(old_ids)))
        db.commit()
    return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    files = candidates()
    print(f"{len(files)} document(s) to re-chunk")
    for file in files:
        if args.dry_run:
            print(f"  would re-chunk {file.filename} ({file.id})")
            continue
        print(f"  {file.filename}: {rechunk(file)} chunks", flush=True)
