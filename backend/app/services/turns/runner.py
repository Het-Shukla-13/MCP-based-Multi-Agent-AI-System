"""
TurnRunner: chat turns run as tasks owned by the server, not by the WebSocket.

Before: the socket handler awaited the whole turn inline. While the turn ran the
socket could not even *read* a "stop" message, and a dropped connection killed
the turn halfway (user message saved, no reply).

Now:
- Each conversation has a *lane*: a FIFO queue plus at most one worker task.
  Turns of one conversation run strictly in order (the second message must see
  the first reply in its history); different conversations run concurrently.
- A turn runs in its own task with its own DB session, so it outlives the socket.
  Events are broadcast to whoever is connected to the conversation *now*.
- Stop = ``task.cancel()``. The streamed text so far is saved as the reply with
  status "stopped", so the conversation never has a question without an answer.
- While running, a heartbeat updates the DB row. The sweeper (startup + periodic)
  closes turns whose owner died (process restart/crash) with an "interrupted"
  reply and resumes turns that were still queued.
- A client that (re)connects receives ``turn_state``: the running turn with its
  draft text so far, and the queue. That is the replay.

Single-process by design (one uvicorn worker). Scaling out means moving the
lanes to a worker process and the broadcast to Redis pub/sub; the DB rows and
the event protocol stay the same.
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

MAX_QUEUED_PER_CONVERSATION = 5
HEARTBEAT_SECONDS = 10
STALE_AFTER_SECONDS = 45
SWEEP_EVERY_SECONDS = 60
MAX_CONTENT_CHARS = 20_000

Broadcast = Callable[[UUID, dict], Awaitable[None]]
Emit = Callable[[dict], Awaitable[None]]


@dataclass
class LiveTurn:
    conversation_id: UUID
    user_id: UUID
    payload: dict[str, Any]
    id: UUID = field(default_factory=uuid4)
    client_id: str | None = None
    status: str = "queued"  # queued | running | done | stopped | failed
    agent: str | None = None
    phase: str | None = None  # last agent_status ("routing", "working", ...)
    draft: str = ""  # streamed text so far: replayed on reconnect, saved on Stop
    user_message_id: UUID | None = None
    task: asyncio.Task | None = field(default=None, repr=False)

    def public(self) -> dict:
        return {
            "turn_id": str(self.id),
            "client_id": self.client_id,
            "status": self.status,
            "content": self.payload.get("content", ""),
            "agent": self.agent,
            "phase": self.phase,
            "draft": self.draft,
            "user_message_id": str(self.user_message_id) if self.user_message_id else None,
        }


class TurnStore(Protocol):
    """Persistence of ChatTurn rows (DB in production, a fake in tests)."""

    async def create(self, turn: LiveTurn) -> None: ...
    async def mark_running(self, turn: LiveTurn) -> None: ...
    async def set_user_message(self, turn: LiveTurn) -> None: ...
    async def heartbeat(self, turn_ids: list[UUID]) -> None: ...
    async def finish(self, turn: LiveTurn, status: str, ai_message_id: UUID | None, error: str | None) -> None: ...
    async def recover(self, live_ids: set[UUID], stale_after: float, on_startup: bool) -> list[LiveTurn]: ...


class TurnExecutor(Protocol):
    """Runs a turn and builds the events/messages around it."""

    async def execute(self, turn: LiveTurn, emit: Emit) -> dict:
        """Run the turn; return the ``chat`` event data (messages already saved)."""

    async def save_stopped(self, turn: LiveTurn) -> dict | None:
        """Persist the partial answer of a stopped turn; return ``chat`` event data."""


class QueueFullError(Exception):
    pass


@dataclass
class _Lane:
    queue: deque[LiveTurn] = field(default_factory=deque)
    current: LiveTurn | None = None
    worker: asyncio.Task | None = None


class TurnRunner:
    def __init__(self, store: TurnStore, executor: TurnExecutor, broadcast: Broadcast):
        self.store = store
        self.executor = executor
        self.broadcast = broadcast
        self._lanes: dict[UUID, _Lane] = {}
        self._background: list[asyncio.Task] = []
        self._closing = False

    # ---- commands (from the WebSocket) -------------------------------------------------

    async def submit(self, conversation_id: UUID, user_id: UUID, payload: dict,
                     client_id: str | None = None, persist: bool = True,
                     turn: LiveTurn | None = None) -> LiveTurn:
        content = (payload.get("content") or "").strip()
        if turn is None:  # (a recovered turn was already validated and stored)
            if not content:
                raise ValueError("Message is empty.")
            if len(content) > MAX_CONTENT_CHARS:
                raise ValueError(f"Message is too long (max {MAX_CONTENT_CHARS} characters).")
        lane = self._lanes.setdefault(conversation_id, _Lane())
        if len(lane.queue) >= MAX_QUEUED_PER_CONVERSATION:
            raise QueueFullError(
                f"{MAX_QUEUED_PER_CONVERSATION} messages are already waiting in this conversation."
            )
        turn = turn or LiveTurn(conversation_id=conversation_id, user_id=user_id,
                                payload=payload, client_id=client_id)
        if persist:
            await self.store.create(turn)
        lane.queue.append(turn)
        await self._send(turn, "turn_queued", {"position": self._position(lane, turn)})
        if self._closing:
            return turn  # stored as queued; picked up after restart
        if lane.worker is None or lane.worker.done():
            lane.worker = asyncio.create_task(self._drain(conversation_id, lane))
        return turn

    async def stop(self, conversation_id: UUID) -> bool:
        """Cancel the running turn of this conversation (queued turns keep waiting)."""
        lane = self._lanes.get(conversation_id)
        if not lane or not lane.current or not lane.current.task or lane.current.task.done():
            return False
        lane.current.task.cancel()
        return True

    async def dequeue(self, conversation_id: UUID, turn_id: UUID) -> bool:
        lane = self._lanes.get(conversation_id)
        if not lane:
            return False
        for turn in list(lane.queue):
            if turn.id == turn_id:
                lane.queue.remove(turn)
                turn.status = "stopped"
                await self.store.finish(turn, "stopped", None, "removed from queue")
                await self._send(turn, "turn_finished", {"status": "stopped"})
                return True
        return False

    def snapshot(self, conversation_id: UUID) -> dict:
        """What a (re)connecting client needs to rebuild the live view."""
        lane = self._lanes.get(conversation_id)
        return {
            "conversation_id": str(conversation_id),
            "current": lane.current.public() if lane and lane.current else None,
            "queued": [t.public() for t in lane.queue] if lane else [],
        }

    # ---- lifecycle --------------------------------------------------------------------

    async def start(self) -> None:
        await self._recover(on_startup=True)
        self._background = [
            asyncio.create_task(self._heartbeat_loop()),
            asyncio.create_task(self._sweep_loop()),
        ]

    async def shutdown(self) -> None:
        # Queued turns stay "queued" in the DB and resume on the next start.
        self._closing = True
        for task in self._background:
            task.cancel()
        # Running turns are cancelled -> partial answer saved as "stopped".
        workers = [lane.worker for lane in self._lanes.values() if lane.worker and not lane.worker.done()]
        for lane in self._lanes.values():
            if lane.current and lane.current.task:
                lane.current.task.cancel()
        if workers:
            await asyncio.wait(workers, timeout=10)

    # ---- internals --------------------------------------------------------------------

    async def _drain(self, conversation_id: UUID, lane: _Lane) -> None:
        while lane.queue and not self._closing:
            turn = lane.queue.popleft()
            lane.current = turn
            try:
                await self._run(turn)
            except Exception:  # never let one turn kill the lane
                logger.exception("Turn bookkeeping failed | turn=%s", turn.id)
            finally:
                lane.current = None
            for waiting in lane.queue:  # positions moved up
                await self._send(waiting, "turn_queued", {"position": self._position(lane, waiting)})
        if not lane.queue and lane.current is None:
            self._lanes.pop(conversation_id, None)

    async def _run(self, turn: LiveTurn) -> None:
        turn.status = "running"
        await self.store.mark_running(turn)
        await self._send(turn, "turn_started", {})

        async def emit(event: dict) -> None:
            await self._on_event(turn, event)

        turn.task = asyncio.create_task(self.executor.execute(turn, emit))
        # asyncio.wait never raises: cancelling turn.task must not cancel the lane worker.
        await asyncio.wait({turn.task})

        if turn.task.cancelled():
            turn.status = "stopped"
            chat = await self.executor.save_stopped(turn)
            if chat:
                await self._send(turn, "chat", chat)
            await self.store.finish(turn, "stopped", _ai_id(chat), None)
        elif (exc := turn.task.exception()) is not None:
            turn.status = "failed"
            logger.error("Turn failed | turn=%s", turn.id, exc_info=exc)
            await self.store.finish(turn, "failed", None, f"{type(exc).__name__}: {exc}"[:500])
            # HTTPException-style errors (file not found, ...) are safe to show.
            detail = getattr(exc, "detail", None)
            await self._send_raw(turn, {
                "type": "error",
                "detail": detail if isinstance(detail, str) else "Failed to process the message.",
                "turn_id": str(turn.id),
                "client_id": turn.client_id,
            })
        else:
            chat = turn.task.result()
            turn.status = "done"
            await self._send(turn, "chat", chat)
            await self.store.finish(turn, "done", _ai_id(chat), None)
        await self._send(turn, "turn_finished", {"status": turn.status})

    async def _on_event(self, turn: LiveTurn, event: dict) -> None:
        status = event.get("status")
        if status == "accepted":
            turn.user_message_id = UUID(event["user_message_id"])
            await self.store.set_user_message(turn)
            return
        if event.get("agent") and event.get("agent") != "root":
            turn.agent = event["agent"]
        if status == "delta":
            turn.draft += event.get("text", "")
            await self._send(turn, "chat_delta", {"agent": event.get("agent"), "text": event.get("text", "")})
        else:
            turn.phase = status
            await self._send(turn, "agent_status", event)

    async def _send(self, turn: LiveTurn, kind: str, data: dict) -> None:
        message = {"type": kind, "data": {
            "conversation_id": str(turn.conversation_id),
            "turn_id": str(turn.id),
            "client_id": turn.client_id,
            **data,
        }}
        await self._send_raw(turn, message)

    async def _send_raw(self, turn: LiveTurn, message: dict) -> None:
        try:
            await self.broadcast(turn.conversation_id, message)
        except Exception:  # a broken socket must never break the turn
            logger.warning("Broadcast failed | turn=%s | type=%s", turn.id, message.get("type"), exc_info=True)

    @staticmethod
    def _position(lane: _Lane, turn: LiveTurn) -> int:
        """1 = next to run after the current turn."""
        return list(lane.queue).index(turn) + 1

    def _running_ids(self) -> list[UUID]:
        return [lane.current.id for lane in self._lanes.values() if lane.current]

    def _live_ids(self) -> set[UUID]:
        ids = set(self._running_ids())
        for lane in self._lanes.values():
            ids.update(t.id for t in lane.queue)
        return ids

    async def _heartbeat_loop(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_SECONDS)
            try:
                if ids := self._running_ids():
                    await self.store.heartbeat(ids)
            except Exception:
                logger.warning("Turn heartbeat failed", exc_info=True)

    async def _sweep_loop(self) -> None:
        while True:
            await asyncio.sleep(SWEEP_EVERY_SECONDS)
            try:
                await self._recover(on_startup=False)
            except Exception:
                logger.warning("Turn sweep failed", exc_info=True)

    async def _recover(self, on_startup: bool) -> None:
        resumable = await self.store.recover(self._live_ids(), STALE_AFTER_SECONDS, on_startup)
        for turn in resumable:
            try:
                await self.submit(turn.conversation_id, turn.user_id, turn.payload,
                                  persist=False, turn=turn)
            except QueueFullError:
                await self.store.finish(turn, "failed", None, "queue full on resume")


def _ai_id(chat: dict | None) -> UUID | None:
    if not chat:
        return None
    ai = chat.get("ai_message") or {}
    return UUID(str(ai["id"])) if ai.get("id") else None
