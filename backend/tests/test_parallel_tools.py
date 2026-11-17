"""Parallel tool calls: scheduler rules, callback wiring, and no blocking calls in async MCP tools."""
import ast
import asyncio
from pathlib import Path

import pytest

from app.agent_layer.agents.general_agent import GeneralAgent
from app.agent_layer.core.tool_scheduler import ToolScheduler, is_write
from app.agent_layer.schemas import AgentContext


class Timeline:
    def __init__(self):
        self.log: list[str] = []
        self.running = 0
        self.max_running = 0


async def call(scheduler, timeline, key, write, seconds=0.05):
    await scheduler.acquire(key, write)
    timeline.running += 1
    timeline.max_running = max(timeline.max_running, timeline.running)
    timeline.log.append(f"start {key}")
    try:
        await asyncio.sleep(seconds)
    finally:
        timeline.running -= 1
        timeline.log.append(f"end {key}")
        await scheduler.release(key)


@pytest.mark.asyncio
async def test_reads_in_one_step_run_concurrently():
    s, t = ToolScheduler(), Timeline()
    started = asyncio.get_running_loop().time()
    await asyncio.gather(*(call(s, t, f"r{i}", False, 0.1) for i in range(3)))
    assert t.max_running == 3
    assert asyncio.get_running_loop().time() - started < 0.2  # ~0.1, not 0.3


@pytest.mark.asyncio
async def test_read_concurrency_is_capped():
    s, t = ToolScheduler(max_parallel_reads=2), Timeline()
    await asyncio.gather(*(call(s, t, f"r{i}", False) for i in range(5)))
    assert t.max_running == 2


@pytest.mark.asyncio
async def test_write_listed_first_still_runs_after_the_steps_reads():
    s, t = ToolScheduler(), Timeline()
    await asyncio.gather(call(s, t, "w", True), call(s, t, "r1", False), call(s, t, "r2", False))
    assert t.log.index("start w") > t.log.index("end r1")
    assert t.log.index("start w") > t.log.index("end r2")


@pytest.mark.asyncio
async def test_writes_are_exclusive_and_serialised():
    s, t = ToolScheduler(), Timeline()
    await asyncio.gather(call(s, t, "w1", True), call(s, t, "w2", True), call(s, t, "w3", True))
    assert t.max_running == 1


@pytest.mark.asyncio
async def test_read_arriving_during_a_write_waits_for_it():
    s, t = ToolScheduler(), Timeline()
    writer = asyncio.create_task(call(s, t, "w", True, 0.1))
    await asyncio.sleep(0.03)  # write is running
    await call(s, t, "late-read", False)
    await writer
    assert t.log.index("start late-read") > t.log.index("end w")


@pytest.mark.asyncio
async def test_release_is_idempotent_and_cancel_frees_the_slot():
    s = ToolScheduler(max_parallel_reads=1)
    await s.acquire("a", False)
    waiting = asyncio.create_task(s.acquire("b", False))  # blocked on the single slot
    await asyncio.sleep(0.01)
    waiting.cancel()
    with pytest.raises(asyncio.CancelledError):
        await waiting
    await s.release("a")
    await s.release("a")  # after_tool + on_tool_error both firing
    assert s.active_reads == 0
    await asyncio.wait_for(s.acquire("c", True), 1)  # nothing leaked: a write can get in


def test_side_effect_classification():
    assert is_write("create_file") and is_write("generate_image") and is_write("create_from_template")
    assert not any(is_write(n) for n in ("web_search", "read_file", "aggregate", "describe_image"))


@pytest.mark.asyncio
async def test_agent_callbacks_apply_the_barrier():
    agent = GeneralAgent()._build_request_agent(
        AgentContext(user_id="u", conversation_id="c", user_message="x"), "gemini-3.1-flash-lite")
    before, after = agent.before_tool_callback, agent.after_tool_callback
    log = []

    class Ctx:
        def __init__(self, call_id):
            self.function_call_id = call_id

    async def run(name, call_id, seconds):
        tool, ctx = type("T", (), {"name": name})(), Ctx(call_id)
        assert await before(tool, {}, ctx) is None
        log.append(f"start {name}")
        await asyncio.sleep(seconds)
        log.append(f"end {name}")
        await after(tool, {}, ctx, {"ok": True})

    await asyncio.gather(run("create_file", "1", 0.01), run("web_search", "2", 0.05), run("fetch_page", "3", 0.05))
    assert log[:2] == ["start web_search", "start fetch_page"]  # reads together, first
    assert log.index("start create_file") > log.index("end fetch_page")


# ---- guard: async MCP tools must not block their server's event loop ----------------

BLOCKING = {
    "_extract_text", "read_csv_robust", "_read_table", "_analyze", "render_markdown_pdf",
    "transcribe_image", "pdf_to_markdown", "read_excel", "ExcelFile", "sleep_sync",
}
BLOCKING_ATTRS = {("time", "sleep"), ("requests", "get"), ("requests", "post")}


def _blocking_calls(func: ast.AsyncFunctionDef) -> list[str]:
    found = []
    for node in ast.walk(func):
        if not isinstance(node, ast.Call):
            continue
        target = node.func
        if isinstance(target, ast.Name) and target.id in BLOCKING:
            found.append(target.id)
        elif isinstance(target, ast.Attribute):
            if target.attr in BLOCKING:
                found.append(target.attr)
            if isinstance(target.value, ast.Name) and (target.value.id, target.attr) in BLOCKING_ATTRS:
                found.append(f"{target.value.id}.{target.attr}")
            # client.models.generate_content(...) is the SYNC Gemini API; .aio.models is async
            if target.attr == "generate_content" and isinstance(target.value, ast.Attribute) \
                    and target.value.attr == "models" and not (
                        isinstance(target.value.value, ast.Attribute) and target.value.value.attr == "aio"):
                found.append("models.generate_content (sync)")
    return found


def test_async_mcp_tools_do_not_call_blocking_functions():
    servers = Path(__file__).parents[1] / "app" / "mcp_servers"
    offenders = {}
    for path in servers.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and (calls := _blocking_calls(node)):
                offenders[f"{path.name}:{node.name}"] = calls
    assert offenders == {}, f"wrap these in asyncio.to_thread: {offenders}"


def test_tool_time_is_wall_time_not_sum():
    from app.services.metrics.collector import tool_wall_ms

    assert tool_wall_ms([(0.0, 0.8), (0.0, 0.8), (0.1, 0.8)]) == 800  # parallel step
    assert tool_wall_ms([(0.0, 1.0), (2.0, 2.5)]) == 1500  # sequential steps
    assert tool_wall_ms([(0.0, 1.0), (0.5, 2.0)]) == 2000  # overlap
    assert tool_wall_ms([]) == 0
