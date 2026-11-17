"""
File ingestion pipeline: parse -> chunk -> embed -> store, plus status updates.

Plain Python with no Celery dependency, so the same code runs in:
  - the Celery worker (app.tasks.file_tasks.process_file wraps it), and
  - the in-process thread pool (FILE_PROCESSING_BACKEND="local").
"""

from uuid import UUID

from loguru import logger

from app.db.database import sync_session_scope
from app.models.chunks import Chunk, ChunkParent
from app.models.file import File
from app.services.embeddings.embedding_utils import embed_texts
from app.services.file_processing.file_processing_service import process_and_chunk


def _set_file_status(file_id: UUID, status: str) -> None:
    with sync_session_scope() as sync_db:
        file = sync_db.get(File, file_id)
        if file:
            file.status = status
            sync_db.add(file)
            sync_db.commit()


def _normalize_processed_chunks(chunks) -> list[dict]:
    """-> [{"content", "metadata", "parent_content" (optional)}], empty chunks dropped."""
    processed_chunks = []
    for chunk in chunks:
        if isinstance(chunk, str):
            item = {"content": chunk.strip(), "metadata": {}}
        elif isinstance(chunk, dict):
            item = {"content": chunk["content"], "metadata": chunk.get("metadata") or {},
                    "parent_content": chunk.get("parent_content")}
        else:
            logger.warning("Skipping invalid chunk type {}", type(chunk).__name__)
            continue
        if item["content"]:
            processed_chunks.append(item)

    if not processed_chunks and chunks:
        raise ValueError("No valid chunks were produced during file processing")
    return processed_chunks


def embedding_text(item: dict) -> str:
    """
    Contextual header: a child from the middle of a section doesn't contain the
    section title, so embed "title + child". Stored content stays the plain child.
    """
    title = (item["metadata"].get("section_title") or "").strip()
    if title and not item["content"].lstrip("# ").startswith(title):
        return f"{title}\n{item['content']}"
    return item["content"]


def _build_rows(file_id: UUID, processed_chunks: list[dict]) -> tuple[list[ChunkParent], list[Chunk]]:
    embeddings = embed_texts([embedding_text(item) for item in processed_chunks]) if processed_chunks else []
    parents: dict[str, ChunkParent] = {}
    chunks = []
    for item, embedding in zip(processed_chunks, embeddings):
        parent_id = None
        parent_key = item["metadata"].get("parent_key")
        if item.get("parent_content") and parent_key is not None:
            if parent_key not in parents:
                parents[parent_key] = ChunkParent(file_id=file_id, content=item["parent_content"])
            parent_id = parents[parent_key].id
        chunks.append(Chunk(file_id=file_id, content=item["content"], file_metadata=item["metadata"],
                            embedding=embedding, parent_id=parent_id))
    return list(parents.values()), chunks


def ingest_file(file_id: str, file_path: str) -> int:
    """Process one uploaded file end to end. Returns the number of stored chunks."""
    file_uuid = UUID(file_id)
    logger.info("File ingestion START | file_id={} | path={}", file_id, file_path)
    _set_file_status(file_uuid, "processing")
    try:
        chunks = process_and_chunk(file_path)
        processed_chunks = _normalize_processed_chunks(chunks)
        parent_rows, chunk_instances = _build_rows(file_uuid, processed_chunks)
        with sync_session_scope() as sync_db:
            sync_db.add_all(parent_rows)
            sync_db.flush()  # parents first: chunks reference them
            sync_db.add_all(chunk_instances)
            sync_db.commit()
        _set_file_status(file_uuid, "processed")
        logger.info("File ingestion DONE | file_id={} | chunks={}", file_id, len(chunk_instances))
        return len(chunk_instances)
    except Exception:
        logger.exception("File ingestion FAILED | file_id={} | path={}", file_id, file_path)
        _set_file_status(file_uuid, "failed")
        raise
