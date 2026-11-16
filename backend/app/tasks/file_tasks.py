from app.core.celery_app import celery_app
from app.services.file_processing.file_ingestion import ingest_file


@celery_app.task(name="app.tasks.file_tasks.process_file")
def process_file(file_id: str, file_path: str) -> int:
    return ingest_file(file_id, file_path)
