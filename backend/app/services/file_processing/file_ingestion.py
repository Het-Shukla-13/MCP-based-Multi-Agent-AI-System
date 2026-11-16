"""
File ingestion pipeline: parse -> chunk -> embed -> store, plus status updates.

Plain Python with no Celery dependency, so the same code runs in:
  - the Celery worker (app.tasks.file_tasks.process_file wraps it), and
  - the in-process thread pool (FILE_PROCESSING_BACKEND="local").
"""

from uuid import UUID

from loguru import logger

from app.db.database import sync_session_scope
from app.models.chunks import Chunk
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


def _normalize_processed_chunks(chunks):
    processed_chunks = []
    for chunk in chunks:
        if isinstance(chunk, str):
            content, file_metadata = chunk.strip(), {}
        elif isinstance(chunk, dict):
            content, file_metadata = chunk["content"], chunk["metadata"]
        else:
            logger.warning("Skipping invalid chunk type {}", type(chunk).__name__)
            continue
        if content:
            processed_chunks.append((content, file_metadata))

    if not processed_chunks and chunks:
        raise ValueError("No valid chunks were produced during file processing")
    return processed_chunks


def _build_chunk_instances(file_id: UUID, processed_chunks):
    embeddings = embed_texts([content for content, _ in processed_chunks]) if processed_chunks else []
    return [
        Chunk(file_id=file_id, content=content, file_metadata=file_metadata, embedding=embedding)
        for (content, file_metadata), embedding in zip(processed_chunks, embeddings)
    ]


def ingest_file(file_id: str, file_path: str) -> int:
    """Process one uploaded file end to end. Returns the number of stored chunks."""
    file_uuid = UUID(file_id)
    logger.info("File ingestion START | file_id={} | path={}", file_id, file_path)
    _set_file_status(file_uuid, "processing")
    try:
        chunks = process_and_chunk(file_path)
        processed_chunks = _normalize_processed_chunks(chunks)
        chunk_instances = _build_chunk_instances(file_uuid, processed_chunks)
        with sync_session_scope() as sync_db:
            sync_db.add_all(chunk_instances)
            sync_db.commit()
        _set_file_status(file_uuid, "processed")
        logger.info("File ingestion DONE | file_id={} | chunks={}", file_id, len(chunk_instances))
        return len(chunk_instances)
    except Exception:
        logger.exception("File ingestion FAILED | file_id={} | path={}", file_id, file_path)
        _set_file_status(file_uuid, "failed")
        raise
