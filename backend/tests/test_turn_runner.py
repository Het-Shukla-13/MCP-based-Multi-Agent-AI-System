"""TurnRunner semantics with a fake store/executor: ordering, stop, queue, replay, recovery."""
import asyncio
from uuid import UUID, uuid4

import pytest

from app.services.turns.runner import MAX_QUEUED_PER_CONVERSATION, LiveTurn, QueueFullError, TurnRunner

CONV, USER = uuid4(), uuid4()


class FakeStore:
    def __init__(self, recoverable=None):
        self.rows: dict[UUID, dict] = {}
        self.recoverable = recoverable or []

    async def create(self, turn): self.rows[turn.id] = {"status": "queued"}
    async def mark_running(self, turn): self.rows.setdefault(turn.id, {})["status"] = "running"
    async def set_user_message(self, turn): self.rows[turn.id]["user_message_id"] = turn.user_message_id
    async def heartbeat(self, ids): pass

    async def finish(self, turn, status, ai_message_id, error):
        self.rows.setdefault(turn.id, {}).update(status=status, ai=ai_message_id, error=error)

    async def recover(self, live_ids, stale_after, on_startup):
        out, self.recoverable = self.recoverable, []
        return out


class FakeExecutor:
    """Streams the message word by word; 'hang' waits until cancelled; 'boom' fails."""

    def __init__(self):
        self.order: list[str] = []
        self.started = asyncio.Event()
        self.stopped_drafts: list[str] = []

    async def execute(self, turn, emit):
        content = turn.payload["content"]
        self.order.append(content)
        await emit({"status": "accepted", "user_message_id": str(uuid4())})
        await emit({"status": "working", "agent": "code"})
        for word in content.split():
            await emit({"status": "delta", "agent": "code", "text": word + " "})
            await asyncio.sleep(0)
        self.started.set()
        if "hang" in content:
            await asyncio.sleep(3600)
        if "boom" in content:
            raise RuntimeError("provider down")
        return {"ai_message": {"id": str(uuid4()), "content": content.upper()}}

    async def save_stopped(self, turn):
        self.stopped_drafts.append(turn.draft)
        return {"ai_message": {"id": str(uuid4()), "content": turn.draft, "status": "stopped"}}


def make_runner(store=None):
    events: list[dict] = []

    async def broadcast(conversation_id, message):
        events.append(message)

    runner = TurnRunner(store or FakeStore(), FakeExecutor(), broadcast)
    return runner, events


async def wait_idle(runner, conversation_id=CONV):
    for _ in range(200):
        lane = runner._lanes.get(conversation_id)
        if lane is None:
            return
        await asyncio.sleep(0.01)
    raise AssertionError("runner never went idle")


def types(events, turn_id=None):
    return [e["type"] for e in events if turn_id is None or e["data"].get("turn_id") == str(turn_id)]


@pytest.mark.asyncio
async def test_turns_in_one_conversation_run_in_order_and_complete():
    runner, events = make_runner()
    first = await runner.submit(CONV, USER, {"content": "one two"}, client_id="c1")
    second = await runner.submit(CONV, USER, {"content": "three"})
    await wait_idle(runner)

    assert runner.executor.order == ["one two", "three"]
    assert types(events, first.id) == [
        "turn_queued", "turn_started", "agent_status", "chat_delta", "chat_delta", "chat", "turn_finished"]
    assert runner.store.rows[first.id]["status"] == "done"
    assert runner.store.rows[second.id]["status"] == "done"
    assert events[0]["data"]["client_id"] == "c1"  # lets the client match its optimistic bubble


@pytest.mark.asyncio
async def test_stop_saves_partial_draft_and_next_queued_turn_still_runs():
    runner, events = make_runner()
    hanging = await runner.submit(CONV, USER, {"content": "partial words hang"})
    after = await runner.submit(CONV, USER, {"content": "next"})
    await runner.executor.started.wait()

    assert await runner.stop(CONV) is True
    await wait_idle(runner)

    assert runner.executor.stopped_drafts == ["partial words hang "]
    assert runner.store.rows[hanging.id]["status"] == "stopped"
    assert runner.store.rows[hanging.id]["ai"] is not None
    finished = [e for e in events if e["type"] == "turn_finished"]
    assert [e["data"]["status"] for e in finished] == ["stopped", "done"]
    assert runner.store.rows[after.id]["status"] == "done"


@pytest.mark.asyncio
async def test_stop_with_nothing_running_returns_false():
    runner, _ = make_runner()
    assert await runner.stop(CONV) is False


@pytest.mark.asyncio
async def test_failed_turn_reports_error_and_lane_continues():
    runner, events = make_runner()
    bad = await runner.submit(CONV, USER, {"content": "boom"})
    good = await runner.submit(CONV, USER, {"content": "fine"})
    await wait_idle(runner)

    assert runner.store.rows[bad.id]["status"] == "failed"
    assert "provider down" in runner.store.rows[bad.id]["error"]
    error = next(e for e in events if e["type"] == "error")
    assert error["detail"] == "Failed to process the message."  # internals not leaked
    assert runner.store.rows[good.id]["status"] == "done"


@pytest.mark.asyncio
async def test_queue_limit_and_dequeue():
    runner, events = make_runner()
    await runner.submit(CONV, USER, {"content": "hang"})
    await runner.executor.started.wait()
    queued = [await runner.submit(CONV, USER, {"content": f"q{i}"}) for i in range(MAX_QUEUED_PER_CONVERSATION)]
    with pytest.raises(QueueFullError):
        await runner.submit(CONV, USER, {"content": "one too many"})

    assert await runner.dequeue(CONV, queued[0].id) is True
    assert runner.store.rows[queued[0].id]["status"] == "stopped"
    assert [t["content"] for t in runner.snapshot(CONV)["queued"]] == ["q1", "q2", "q3", "q4"]
    await runner.stop(CONV)
    await wait_idle(runner)
    assert runner.executor.order[1:] == ["q1", "q2", "q3", "q4"]


@pytest.mark.asyncio
async def test_snapshot_replays_running_draft_and_queue():
    runner, _ = make_runner()
    await runner.submit(CONV, USER, {"content": "streaming text hang"})
    await runner.submit(CONV, USER, {"content": "waiting"})
    await runner.executor.started.wait()

    snap = runner.snapshot(CONV)
    assert snap["current"]["status"] == "running"
    assert snap["current"]["draft"] == "streaming text hang "
    assert snap["current"]["agent"] == "code"
    assert snap["current"]["user_message_id"] is not None
    assert [t["content"] for t in snap["queued"]] == ["waiting"]
    await runner.stop(CONV)
    await wait_idle(runner)
    assert runner.snapshot(CONV) == {"conversation_id": str(CONV), "current": None, "queued": []}


@pytest.mark.asyncio
async def test_conversations_run_concurrently():
    runner, _ = make_runner()
    other = uuid4()
    await runner.submit(CONV, USER, {"content": "hang here"})
    await runner.executor.started.wait()
    await runner.submit(other, USER, {"content": "quick"})
    await wait_idle(runner, other)  # finished although CONV is still busy
    assert "quick" in runner.executor.order
    await runner.stop(CONV)
    await wait_idle(runner)


@pytest.mark.asyncio
async def test_empty_and_oversized_messages_rejected():
    runner, _ = make_runner()
    with pytest.raises(ValueError):
        await runner.submit(CONV, USER, {"content": "   "})
    with pytest.raises(ValueError):
        await runner.submit(CONV, USER, {"content": "x" * 20_001})


@pytest.mark.asyncio
async def test_startup_resumes_recovered_turns_without_recreating_rows():
    recovered = LiveTurn(conversation_id=CONV, user_id=USER, payload={"content": "left over"})
    store = FakeStore(recoverable=[recovered])
    runner, _ = make_runner(store)
    await runner.start()
    await wait_idle(runner)
    await runner.shutdown()

    assert runner.executor.order == ["left over"]
    assert store.rows[recovered.id]["status"] == "done"


@pytest.mark.asyncio
async def test_shutdown_keeps_queue_for_next_start():
    runner, _ = make_runner()
    await runner.submit(CONV, USER, {"content": "hang"})
    waiting = await runner.submit(CONV, USER, {"content": "later"})
    await runner.executor.started.wait()
    await runner.shutdown()

    assert "later" not in runner.executor.order
    assert runner.store.rows[waiting.id]["status"] == "queued"  # resumed by recover() next start


@pytest.mark.asyncio
async def test_broken_broadcast_does_not_break_the_turn():
    async def broken(conversation_id, message):
        raise ConnectionError("socket gone")

    runner = TurnRunner(FakeStore(), FakeExecutor(), broken)
    turn = await runner.submit(CONV, USER, {"content": "still saved"})
    await wait_idle(runner)
    assert runner.store.rows[turn.id]["status"] == "done"
