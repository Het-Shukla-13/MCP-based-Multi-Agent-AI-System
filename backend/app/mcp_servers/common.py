"""Shared helpers for MCP servers: logging to stderr, ownership checks, output limits."""

import sys
from uuid import UUID

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import File

MAX_TOOL_OUTPUT_CHARS = 12_000  # keep tool results small enough for the model context


def configure_server_logging(server_name: str) -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", format=f"[mcp:{server_name}] {{time:HH:mm:ss}} | {{level}} | {{message}}")


def truncate(text: str, limit: int = MAX_TOOL_OUTPUT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n\n[... truncated {len(text) - limit} characters]"


def parse_uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ValueError(f"Invalid {field}") from exc


async def get_owned_files(db: AsyncSession, user_id: UUID, conversation_id: UUID) -> list[File]:
    """Only files of THIS user in THIS conversation are ever visible to tools."""
    result = await db.execute(
        select(File)
        .where(File.user_id == user_id, File.conversation_id == conversation_id)
        .order_by(File.created_at)
    )
    return list(result.scalars().all())


def match_file(files: list[File], file_name: str) -> File | None:
    wanted = file_name.strip().casefold()
    for f in files:
        if f.filename.casefold() == wanted:
            return f
    for f in files:  # tolerate partial names ("report" -> "Q3 report.pdf")
        if wanted and wanted in f.filename.casefold():
            return f
    return None


async def resolve_owned_file(user_id: str, conversation_id: str, file_name: str) -> tuple[File | None, str]:
    """Return (file, error_message). Ownership is enforced by user + conversation."""
    from app.db.database import AsyncSessionLocal

    uid, cid = parse_uuid(user_id, "user_id"), parse_uuid(conversation_id, "conversation_id")
    async with AsyncSessionLocal() as db:
        files = await get_owned_files(db, uid, cid)
    target = match_file(files, file_name)
    if target is None:
        names = ", ".join(f.filename for f in files) or "none"
        return None, f"No uploaded file matches '{file_name}'. Available files: {names}"
    return target, ""


GENERATED_FILE_MARKER = "generated_file_id"


async def save_generated_file(user_id: str, conversation_id: str, filename: str, data: bytes, mime_type: str) -> dict:
    """
    Store bytes produced by a tool and register them as a conversation file.
    Returns ids/URLs; the agent layer finds GENERATED_FILE_MARKER in the tool
    result and attaches the file to the assistant's reply.
    """
    from app.core.config import BACKEND_ROOT
    from app.crud.file import create_file
    from app.db.database import AsyncSessionLocal
    from app.schemas.file import FileCreate

    out_dir = BACKEND_ROOT / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(data)

    async with AsyncSessionLocal() as db:
        record = await create_file(
            db,
            FileCreate(
                conversation_id=parse_uuid(conversation_id, "conversation_id"),
                user_id=parse_uuid(user_id, "user_id"),
                filename=filename,
                file_type=mime_type,
                file_size=len(data),
                storage_path=str(path),
                status="processed",
            ),
        )
        await db.commit()
    file_id = str(record.id)
    return {
        GENERATED_FILE_MARKER: file_id,
        "filename": filename,
        "download_url": f"/files/generated/{file_id}/download",
        "preview_url": f"/files/generated/{file_id}/preview",
    }
