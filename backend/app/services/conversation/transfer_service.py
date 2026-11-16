"""Conversation export/import (portable JSON)."""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.conversation import get_conversation
from app.models import Conversation, Message
from app.schemas.import_convo import EXPORT_FORMAT, EXPORT_VERSION, ImportConversationRequest
from app.services.conversation.history_service import fetch_conversation_history
from app.services.memory.background_memory_pipeline import schedule_memory_maintenance_pipeline
from app.services.tokenization.tokenizer import get_token_count

# Internal state is recomputed after import, so it is not exported.
INTERNAL_METADATA_KEYS = {"stm", "agent_state"}


def _portable_metadata(metadata: dict | None) -> dict:
    return {k: v for k, v in (metadata or {}).items() if k not in INTERNAL_METADATA_KEYS}


async def export_conversation(db: AsyncSession, conversation_id: UUID) -> dict:
    conversation = await get_conversation(db, conversation_id)  # 404 if missing
    messages = await fetch_conversation_history(db, conversation_id, limit=10_000)
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "convo_metadata": _portable_metadata(conversation.convo_metadata),
        "messages": [
            {
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat(),
                # File bytes are not exported; names are kept for context.
                "files": [f.filename for f in (m.files or [])],
            }
            for m in messages
        ],
    }


async def import_messages(
    db: AsyncSession,
    *,
    conversation: Conversation,
    payload: ImportConversationRequest,
) -> int:
    if payload.format not in (None, EXPORT_FORMAT):
        raise HTTPException(status_code=400, detail=f"Unsupported format: {payload.format}")

    # Keep original timestamps when given; otherwise space messages 1 ms apart so
    # their order is preserved (history is sorted by created_at).
    base_time = datetime.utcnow()
    rows = []
    for index, item in enumerate(payload.messages):
        rows.append(
            Message(
                conversation_id=conversation.id,
                user_id=conversation.user_id,
                role=item.role,
                content=item.content,
                token_count=get_token_count(item.content),  # was 0, which broke the STM token window
                created_at=(item.created_at.replace(tzinfo=None) if item.created_at else base_time + timedelta(milliseconds=index)),
            )
        )

    if payload.title:
        conversation.title = payload.title
    if payload.convo_metadata:
        conversation.convo_metadata = {
            **(conversation.convo_metadata or {}),
            **_portable_metadata(payload.convo_metadata),
        }

    db.add_all(rows)  # one transaction instead of one commit per message
    db.add(conversation)
    await db.commit()

    # Rebuild long-term memory, metadata and profile from the imported turns,
    # exactly as if they had been chatted live.
    schedule_memory_maintenance_pipeline(user_id=conversation.user_id, conversation_id=conversation.id)
    return len(rows)
