"""Production TurnStore (chat_turn rows) and TurnExecutor (the real chat pipeline)."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update

from app.agent_layer.core.state import set_active_agent
from app.crud.conversation import get_conversation, update_conversation_metadata
from app.crud.message import create_message, get_message
from app.db.database import AsyncSessionLocal
from app.models import ChatTurn
from app.schemas.message import MessageRead
from app.services.message.message_service import build_ai_message_payload, send_message_from_payload
from app.services.tokenization.token_service import get_message_token_count
from app.services.turns.runner import Emit, LiveTurn

logger = logging.getLogger(__name__)

STOPPED_EMPTY_REPLY = "_Stopped before any answer was written._"
INTERRUPTED_REPLY = (
    "_This reply was interrupted (the server restarted while it was being written). "
    "Please send your message again._"
)


def chat_event_data(conversation_id, user_message, ai_message, active_agent, agent_switched, error) -> dict:
    """The ``chat`` event payload: same shape the frontend already consumes."""
    return jsonable_encoder({
        "conversation_id": str(conversation_id),
        "user_message": MessageRead.model_validate(user_message).model_dump(),
        "ai_message": MessageRead.model_validate(ai_message).model_dump(),
        "active_agent": active_agent,
        "agent_switched": agent_switched,
        "error": error,
    })


async def _answer(db, user_message, content: str, agent: str | None, status: str):
    """Save an assistant message that closes a turn which didn't finish normally."""
    payload = build_ai_message_payload(user_message, content, agent_name=agent)
    payload.status = status
    payload.token_count = get_message_token_count(payload)
    return await create_message(db, payload)


class DbTurnStore:

    async def create(self, turn: LiveTurn) -> None:
        async with AsyncSessionLocal() as db:
            db.add(ChatTurn(id=turn.id, conversation_id=turn.conversation_id, user_id=turn.user_id,
                            payload=turn.payload, status="queued"))
            await db.commit()

    async def _update(self, turn_id: UUID, **values) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(update(ChatTurn).where(ChatTurn.id == turn_id).values(**values))
            await db.commit()

    async def mark_running(self, turn: LiveTurn) -> None:
        now = datetime.utcnow()
        await self._update(turn.id, status="running", started_at=now, heartbeat_at=now)

    async def set_user_message(self, turn: LiveTurn) -> None:
        await self._update(turn.id, user_message_id=turn.user_message_id)

    async def heartbeat(self, turn_ids: list[UUID]) -> None:
        async with AsyncSessionLocal() as db:
            await db.execute(update(ChatTurn).where(ChatTurn.id.in_(turn_ids))
                             .values(heartbeat_at=datetime.utcnow()))
            await db.commit()

    async def finish(self, turn: LiveTurn, status: str, ai_message_id: UUID | None, error: str | None) -> None:
        await self._update(turn.id, status=status, ai_message_id=ai_message_id, error=error,
                           finished_at=datetime.utcnow())

    async def recover(self, live_ids: set[UUID], stale_after: float, on_startup: bool) -> list[LiveTurn]:
        """
        Close turns whose owner is gone; return turns that can safely run again.

        - running, user message saved, no reply  -> "interrupted" reply, row interrupted
        - running, user message NOT saved yet     -> nothing happened yet: requeue (startup)
        - queued (startup only: the old process's queue) -> requeue in order
        On a periodic sweep only rows with a stale heartbeat that this process does
        not own are touched (a live turn's heartbeat is at most HEARTBEAT_SECONDS old).
        """
        cutoff = datetime.utcnow() - timedelta(seconds=stale_after)
        resumable: list[LiveTurn] = []
        async with AsyncSessionLocal() as db:
            query = select(ChatTurn).where(ChatTurn.status.in_(("running", "queued")))
            rows = (await db.execute(query.order_by(ChatTurn.created_at))).scalars().all()
            for row in rows:
                if row.id in live_ids:
                    continue
                if not on_startup and (row.status == "queued" or (row.heartbeat_at or row.created_at) > cutoff):
                    continue
                if row.status == "running" and row.user_message_id and not row.ai_message_id:
                    try:
                        user_message = await get_message(db, row.user_message_id)
                        ai = await _answer(db, user_message, INTERRUPTED_REPLY, None, "interrupted")
                        row.ai_message_id = ai.id
                    except Exception:
                        logger.warning("Could not answer interrupted turn %s", row.id, exc_info=True)
                    row.status, row.error, row.finished_at = "interrupted", "owner died", datetime.utcnow()
                    db.add(row)
                    logger.warning("Turn interrupted | turn=%s | conversation=%s", row.id, row.conversation_id)
                elif row.status == "running" and row.ai_message_id:
                    row.status, row.finished_at = "done", datetime.utcnow()  # died after saving the reply
                    db.add(row)
                else:  # queued, or running before anything was saved
                    row.status = "queued"
                    db.add(row)
                    resumable.append(LiveTurn(id=row.id, conversation_id=row.conversation_id,
                                              user_id=row.user_id, payload=row.payload))
            await db.commit()
        if resumable:
            logger.info("Resuming %d queued turn(s)", len(resumable))
        return resumable


class ChatTurnExecutor:

    async def execute(self, turn: LiveTurn, emit: Emit) -> dict:
        # Own session: the turn outlives the WebSocket (and its request-scoped session).
        async with AsyncSessionLocal() as db:
            result = await send_message_from_payload(
                db, turn.conversation_id, turn.payload, turn.user_id, on_status=emit
            )
        return chat_event_data(
            turn.conversation_id, result["user_message"], result["ai_message"],
            result.get("active_agent", "general"), result.get("agent_switched", False),
            result.get("error", False),
        )

    async def save_stopped(self, turn: LiveTurn) -> dict | None:
        if turn.user_message_id is None:
            return None  # stopped before the user message was saved: nothing to answer
        async with AsyncSessionLocal() as db:
            user_message = await get_message(db, turn.user_message_id)
            content = turn.draft.strip() or STOPPED_EMPTY_REPLY
            ai = await _answer(db, user_message, content, turn.agent, "stopped")
            if turn.agent:  # keep follow-ups sticky to the agent that was answering
                conversation = await get_conversation(db, turn.conversation_id)
                await update_conversation_metadata(
                    db, turn.conversation_id, set_active_agent(conversation.convo_metadata, turn.agent))
            return chat_event_data(turn.conversation_id, user_message, ai,
                                   turn.agent or "general", False, False)
