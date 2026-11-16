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
