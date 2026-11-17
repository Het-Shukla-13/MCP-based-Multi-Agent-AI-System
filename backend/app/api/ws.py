import json
import logging
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlmodel import select

from app.agent_layer.core import agent_registry
from app.core.security import decode_access_token
from app.core.websocket import manager
from app.db.database import AsyncSessionLocal
from app.models import Conversation
from app.services.turns import QueueFullError, turn_runner

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/ws",
    tags=["WebSockets"],
)


@router.get("/agents")
async def list_agents():
    """Agents straight from the registry: the same descriptions the root agent routes on."""
    return {
        "agents": [
            {"name": agent.name, "label": agent.label, "description": agent.description}
            for agent in agent_registry.get_all().values()
        ]
    }


@router.websocket("/{conversation_id}")
async def websocket_endpoint(websocket: WebSocket, conversation_id: UUID):
    """
    Command channel for one conversation. Turns are run by the TurnRunner, not
    here, so this loop keeps reading while a reply is being written.

    Client -> server:
      {"content": "...", "file_ids": [...], "selected_agent": ..., "format": ..., "client_id": ...}
                                         (no "type", or "type": "send") -> queue a turn
      {"type": "stop"}                   -> cancel the running turn (partial answer is kept)
      {"type": "dequeue", "turn_id": ..} -> remove a queued turn
    Server -> client:
      turn_state (on connect: running turn + draft + queue), turn_queued, turn_started,
      agent_status, chat_delta, chat (saved messages), turn_finished, error
    """
    # Browsers can't set headers on a WebSocket, so the access token comes as
    # ?token=. The user id is DERIVED from it; a client-supplied user_id is ignored.
    user_id = decode_access_token(websocket.query_params.get("token") or "")
    if user_id is None:
        await websocket.close(code=1008)  # 1008 = policy violation
        return

    # Short-lived session: holding one for the socket's lifetime kept a DB
    # transaction open while the user was idle.
    async with AsyncSessionLocal() as db:
        owned = (await db.execute(
            select(Conversation.id).where(Conversation.id == conversation_id, Conversation.user_id == user_id)
        )).scalar_one_or_none()
    if not owned:
        await websocket.close(code=1008)
        return

    await manager.connect(conversation_id, websocket)
    # Replay: a client (re)connecting mid-turn gets the draft so far and the queue.
    await websocket.send_json({"type": "turn_state", "data": turn_runner.snapshot(conversation_id)})

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                command = json.loads(raw)
                if not isinstance(command, dict):
                    raise ValueError("Expected a JSON object.")
                kind = command.get("type") or "send"
                if kind == "stop":
                    stopped = await turn_runner.stop(conversation_id)
                    if not stopped:
                        await websocket.send_json({"type": "error", "detail": "Nothing is running."})
                elif kind == "dequeue":
                    await turn_runner.dequeue(conversation_id, UUID(str(command.get("turn_id"))))
                elif kind == "send":
                    payload = {k: command.get(k) for k in ("content", "file_ids", "selected_agent", "format")}
                    payload["file_ids"] = [str(f) for f in (payload["file_ids"] or [])]
                    client_id = command.get("client_id")
                    await turn_runner.submit(conversation_id, user_id, payload,
                                             client_id=str(client_id)[:64] if client_id else None)
                else:
                    raise ValueError(f"Unknown command type: {kind}")
            except (QueueFullError, ValueError) as exc:
                await websocket.send_json({"type": "error", "detail": str(exc)})
            except Exception:
                logger.exception("WebSocket command failed | conversation=%s", conversation_id)
                await websocket.send_json({"type": "error", "detail": "Failed to process the message."})
    except WebSocketDisconnect:
        pass  # running turns continue; their result is saved and replayed on reconnect
    finally:
        manager.disconnect(conversation_id, websocket)
