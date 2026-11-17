"""Server-owned chat turns: queue, stop, heartbeat/sweeper, replay. See runner.py."""
from app.core.websocket import manager
from app.services.turns.db import ChatTurnExecutor, DbTurnStore
from app.services.turns.runner import LiveTurn, QueueFullError, TurnRunner



async def _broadcast(conversation_id, message: dict) -> None:
    await manager.send_to_conversation(message, conversation_id)


turn_runner = TurnRunner(DbTurnStore(), ChatTurnExecutor(), _broadcast)

__all__ = ["turn_runner", "TurnRunner", "LiveTurn", "QueueFullError"]
