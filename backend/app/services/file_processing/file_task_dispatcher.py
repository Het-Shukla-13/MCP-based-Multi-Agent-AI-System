from concurrent.futures import Future, ThreadPoolExecutor

from fastapi import BackgroundTasks
from kombu.exceptions import OperationalError
from loguru import logger

from app.core.config import settings

LOCAL_FILE_TASK_EXECUTOR: ThreadPoolExecutor | None = None


def get_local_file_task_executor() -> ThreadPoolExecutor:
    global LOCAL_FILE_TASK_EXECUTOR
    if LOCAL_FILE_TASK_EXECUTOR is None:
        LOCAL_FILE_TASK_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="file-ingest")
    return LOCAL_FILE_TASK_EXECUTOR


def shutdown_local_file_task_executor() -> None:
    global LOCAL_FILE_TASK_EXECUTOR
    if LOCAL_FILE_TASK_EXECUTOR is not None:
        LOCAL_FILE_TASK_EXECUTOR.shutdown(wait=True)
        LOCAL_FILE_TASK_EXECUTOR = None


def _log_job_outcome(file_id: str, future: Future) -> None:
    # A ThreadPoolExecutor stores a job's exception inside its Future. If nobody
    # inspects the Future, the error vanishes silently, so we always inspect it.
    exc = future.exception()
    if exc is not None:
        logger.opt(exception=exc).error("Local file job crashed | file_id={}", file_id)


def _submit_local_file_processing(file_id: str, storage_path: str) -> None:
    # Plain function, NOT the Celery task object: calling a Celery task directly
    # from pool threads fails (its per-thread request stack only exists in the
    # main thread), which made every concurrent job after the first one crash.
    from app.services.file_processing.file_ingestion import ingest_file

    future = get_local_file_task_executor().submit(ingest_file, file_id, storage_path)
    future.add_done_callback(lambda f: _log_job_outcome(file_id, f))


def _enqueue_with_celery(file_id: str, storage_path: str) -> None:
    from app.core.celery_app import celery_app

    celery_app.send_task("app.tasks.file_tasks.process_file", args=[file_id, storage_path])


def queue_file_processing(background_tasks: BackgroundTasks, file_id: str, storage_path: str) -> None:
    if settings.FILE_PROCESSING_BACKEND == "celery" and settings.CELERY_BROKER_URL:
        try:
            _enqueue_with_celery(file_id, storage_path)
            return
        except OperationalError:
            logger.warning("Celery broker unavailable; processing file {} in-process", file_id)

    background_tasks.add_task(_submit_local_file_processing, file_id, storage_path)
