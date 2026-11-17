"""Human-in-the-loop tool confirmation: callback policy + runner transport."""
import asyncio
from uuid import uuid4

import pytest

from app.agent_layer.agents.general_agent import GeneralAgent
from app.agent_layer.core.confirmation import Decision, current_confirmer, preview_args, tool_response_for
from app.agent_layer.schemas import AgentContext
from app.services.metrics.collector import TurnCollector, current_turn
from app.services.turns.runner import TurnRunner
from tests.test_turn_runner import FakeStore, wait_idle

CONV, USER = uuid4(), uuid4()


def callback():
    agent = GeneralAgent()._build_request_agent(
        AgentContext(user_id="u1", conversation_id="c1", user_message="x"), "gemini-3.1-flash-lite")
    return agent.before_tool_callback


class Ctx:
    function_call_id = "call-1"


def tool(name):
    return type("T", (), {"name": name})()


async def run_callback(name, args, confirmer):
    token = current_confirmer.set(confirmer)
    try:
        return await callback()(tool(name), args, Ctx())
    finally:
        current_confirmer.reset(token)


@pytest.mark.asyncio
async def test_side_effect_tool_waits_and_user_sees_no_identity_args():
    asked = []

    async def confirmer(agent, name, args, call_id):
        asked.append((agent, name, args, call_id))
        return Decision("approve")

    args = {"filename": "r.md", "content": "hello", "user_id": "forged"}
    assert await run_callback("create_file", args, confirmer) is None  # approved -> tool runs
    assert asked == [("general", "create_file", {"filename": "r.md", "content": "hello"}, "call-1")]
    assert args["user_id"] == "u1"  # identity still enforced


@pytest.mark.asyncio
async def test_read_only_tools_never_ask():
    async def confirmer(*_):
        raise AssertionError("should not be asked")

    assert await run_callback("search_files", {"query": "q"}, confirmer) is None


@pytest.mark.asyncio
async def test_without_a_connected_human_calls_proceed():
    assert await callback()(tool("create_file"), {"filename": "a"}, Ctx()) is None


@pytest.mark.asyncio
async def test_reject_and_revise_become_the_tool_result():
    async def reject(*_):
        return Decision("reject")

    async def revise(*_):
        return Decision("revise", "call it summary.md")

    rejected = await run_callback("generate_image", {"prompt": "cat"}, reject)
    assert rejected["status"] == "rejected" and "Do not call generate_image again" in rejected["instruction"]
    revised = await run_callback("create_file", {"filename": "a.md"}, revise)
    assert revised["status"] == "revision_requested"
    assert revised["user_feedback"] == "call it summary.md"


def test_preview_truncates_long_content():
    preview = preview_args({"content": "x" * 5000, "user_id": "u"}, ("user_id",))
    assert "user_id" not in preview and len(preview["content"]) < 1600
    assert tool_response_for("create_file", Decision("expired"))["status"] == "rejected"


# ---- runner transport -------------------------------------------------------------

class ConfirmingExecutor:
    """Acts like an agent that calls create_file twice; records what came back."""

    def __init__(self):
        self.results = []

    async def execute(self, turn, emit):
        collector = TurnCollector(user_id=USER, conversation_id=CONV)
        current_turn.set(collector)
        for name in ("one.md", "two.md"):
            confirmer = current_confirmer.get()
            if confirmer is None:  # same rule as the real callback: nobody to ask -> proceed
                self.results.append("auto")
                continue
            decision = await confirmer("document", "create_file", {"filename": name}, name)
            self.results.append(decision.action)
        self.collector = collector
        return {"ai_message": {"id": str(uuid4())}}

    async def save_stopped(self, turn):
        return None


def make():
    events = []

    async def broadcast(_, message):
        events.append(message)

    return TurnRunner(FakeStore(), ConfirmingExecutor(), broadcast), events


async def next_confirmation(runner, events, seen):
    for _ in range(200):
        pending = [e for e in events if e["type"] == "tool_confirmation"]
        if len(pending) > seen:
            return pending[-1]["data"]
        await asyncio.sleep(0.01)
    raise AssertionError("no confirmation requested")


@pytest.mark.asyncio
async def test_runner_round_trip_snapshot_and_metrics():
    runner, events = make()
    await runner.submit(CONV, USER, {"content": "make files", "confirm_tools": True})
    first = await next_confirmation(runner, events, 0)
    assert first["tool"] == "create_file" and first["args"] == {"filename": "one.md"}

    snap = runner.snapshot(CONV)["current"]  # reconnect while waiting: prompt is replayed
    assert snap["phase"] == "awaiting_confirmation"
    assert [p["confirmation_id"] for p in snap["pending_confirmations"]] == [first["confirmation_id"]]

    with pytest.raises(ValueError):
        await runner.confirm(CONV, first["confirmation_id"], "revise", "")  # feedback required
    await asyncio.sleep(0.05)
    assert await runner.confirm(CONV, first["confirmation_id"], "reject") is True
    assert await runner.confirm(CONV, first["confirmation_id"], "approve") is False  # already answered

    second = await next_confirmation(runner, events, 1)
    assert await runner.confirm(CONV, second["confirmation_id"], "approve") is True
    await wait_idle(runner, CONV)

    assert runner.executor.results == ["reject", "approve"]
    resolved = [e["data"]["decision"] for e in events if e["type"] == "tool_confirmation_resolved"]
    assert resolved == ["reject", "approve"]
    assert runner.executor.collector.confirm_ms >= 40  # human wait recorded separately


@pytest.mark.asyncio
async def test_approve_all_skips_later_prompts_in_the_same_turn():
    runner, events = make()
    await runner.submit(CONV, USER, {"content": "make files", "confirm_tools": True})
    first = await next_confirmation(runner, events, 0)
    await runner.confirm(CONV, first["confirmation_id"], "approve_all")
    await wait_idle(runner, CONV)
    assert runner.executor.results == ["approve_all", "approve"]
    assert len([e for e in events if e["type"] == "tool_confirmation"]) == 1


@pytest.mark.asyncio
async def test_timeout_counts_as_rejection(monkeypatch):
    monkeypatch.setattr("app.services.turns.runner.CONFIRMATION_TIMEOUT_SECONDS", 0.05)
    runner, events = make()
    await runner.submit(CONV, USER, {"content": "make files", "confirm_tools": True})
    await wait_idle(runner, CONV)
    assert runner.executor.results == ["expired", "expired"]


@pytest.mark.asyncio
async def test_stop_while_waiting_for_confirmation():
    runner, events = make()
    turn = await runner.submit(CONV, USER, {"content": "make files", "confirm_tools": True})
    await next_confirmation(runner, events, 0)
    assert await runner.stop(CONV) is True
    await wait_idle(runner, CONV)
    assert runner.store.rows[turn.id]["status"] == "stopped"


@pytest.mark.asyncio
async def test_unknown_decision_rejected():
    runner, _ = make()
    with pytest.raises(ValueError):
        await runner.confirm(CONV, "x", "maybe")


def test_collector_excludes_wait_from_tool_time():
    c = TurnCollector(user_id=USER, conversation_id=CONV)
    c.tool_started("call-1", "create_file", {})
    c.add_confirmation_wait("call-1", 10_000)
    c.tool_finished("call-1", "create_file", ok=True)
    assert c.tools[0]["ms"] == 0 and c.confirm_ms == 10_000


@pytest.mark.asyncio
async def test_clients_that_did_not_opt_in_are_never_asked():
    runner, events = make()
    await runner.submit(CONV, USER, {"content": "make files"})  # old UI: no confirm_tools
    for _ in range(100):
        if runner.executor.results:
            break
        await asyncio.sleep(0.01)
    await wait_idle(runner, CONV)
    assert runner.executor.results == ["auto", "auto"]
    assert not [e for e in events if e["type"] == "tool_confirmation"]
