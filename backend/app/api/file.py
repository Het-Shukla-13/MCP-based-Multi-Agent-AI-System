import os
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, File as FastAPIFile, Query, Response, UploadFile
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user, owned_conversation, owned_file
from app.core.config import BACKEND_ROOT
from app.crud.file import create_file, get_file, get_files, validate_and_save_file_to_storage
from app.db.database import get_db
from app.models import User
from app.schemas.file import FileCreate, FileRead
from app.services.file_processing.file_task_dispatcher import queue_file_processing

router = APIRouter(prefix="/files", tags=["Files"])

# Files may only be deleted from inside these folders (defence in depth: a corrupted
# storage_path must never let a delete reach anything else on disk).
_STORAGE_ROOTS = [(BACKEND_ROOT / "uploads").resolve(), (BACKEND_ROOT / "generated").resolve()]


@router.post("/upload", response_model=list[FileRead])
async def upload_file(
    background_tasks: BackgroundTasks,
    conversation_id: UUID = Query(...),
    files: list[UploadFile] = FastAPIFile(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await owned_conversation(db, conversation_id, user)
    created_files, queued_jobs = [], []
    for file in files:
        path, size, mime_type = await validate_and_save_file_to_storage(file)
        file_created = await create_file(db, FileCreate(
            conversation_id=conversation_id,
            user_id=user.id,
            filename=file.filename,
            file_type=mime_type,  # verified from content, not the client's claim
            file_size=size,
            storage_path=path,
        ))
        queued_jobs.append((str(file_created.id), file_created.storage_path))
        created_files.append(FileRead(**file_created.model_dump()))

    await db.commit()
    for file_id, storage_path in queued_jobs:
        queue_file_processing(background_tasks, file_id, storage_path)
    return created_files


@router.get("/", response_model=list[FileRead])
async def read_all(conversation_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_conversation(db, conversation_id, user)
    return await get_files(db, conversation_id)


@router.get("/{file_id}", response_model=FileRead)
async def read(file_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await owned_file(db, file_id, user)
    return await get_file(db, file_id)


@router.delete("/{file_id}", status_code=204)
async def delete(file_id: UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Delete the record (chunks cascade in the DB) and the stored bytes."""
    file = await owned_file(db, file_id, user)
    path = Path(file.storage_path).resolve()
    await db.delete(file)
    await db.commit()
    if any(path.is_relative_to(root) for root in _STORAGE_ROOTS) and path.exists():
        os.remove(path)
    return Response(status_code=204)
