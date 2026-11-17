# 38 — Parallel tools: real concurrency, a write barrier, honest metrics

Branch: `feature/parallel-tools` (Phase G)

## Starting point: ADK already runs tools in parallel… on paper

When the model asks for several tools in one step, ADK starts them all with `asyncio.gather` (`flows/llm_flows/functions.py`). So the first job wasn't "add parallelism". It was **checking that it actually happens end to end**.

The path of one tool call:

```
ADK gather -> our before_tool callback -> McpTool -> shared MCP ClientSession (stdio)
           -> FastMCP server process (one event loop) -> tool function
```

- The ADK session manager only locks while *getting* the session. `call_tool` requests are multiplexed by JSON-RPC id.
- The MCP server starts one task per request (`tg.start_soon(self._handle_message…)`).
- **So everything is concurrent unless a tool blocks its server's event loop.**

## Finding 1: blocking calls inside `async def` tools

`read_file` on an image called the **synchronous** Gemini OCR API (`client.models.generate_content`, not `client.aio.models…`). PDF/DOCX parsing, pandas loading, PDF rendering and tree-sitter analysis also ran inline.

`async def` does not make code non-blocking. A blocking call inside it freezes the entire event loop of that MCP server, which means **every other user's** call to that server too.

Measured through a real stdio MCP session: how long `list_files` takes while an image OCR is in flight.

| | list_files latency |
|---|---|
| before | **2.87 s** (waited for the OCR to finish) |
| after (`asyncio.to_thread`) | **0.01 s** |

CPU-bound work (pandas on 400k rows) only gained ×1.2, because threads share the GIL. Offloading it still matters: it stops a heavy call from freezing the *network-bound* calls next to it. Web search (already threaded) runs ×2.2–2.4 faster concurrently.

**Guard test:** `test_async_mcp_tools_do_not_call_blocking_functions` parses every MCP server with `ast` and fails if an `async def` *calls* a known-blocking function or the sync Gemini API directly. `asyncio.to_thread(fn, …)` passes `fn` as a value instead of calling it, so it isn't flagged. Run against the old code, the test listed all five offenders.

## Finding 2: concurrency needs rules: `ToolScheduler`

`app/agent_layer/core/tool_scheduler.py` is a per-turn **readers-writer lock**:

| Call | Rule |
|---|---|
| read (search, read_file, fetch_page, aggregate…) | shared, at most 4 at once (politeness to providers) |
| write (`create_file`, `create_from_template`, `generate_image`) | exclusive, one at a time, **after** the reads of its step |
| read arriving while a write runs | waits for it |

Why these rules:

- **Snapshot semantics.** The model planned the step against the state it had *before* the step, so reads go first and writes after them.
- **One prompt at a time.** Writes now ask for confirmation (note 37). Two writes at once would mean two prompts at once.

**The settle trick.** `gather` creates every task of a step before any of them runs, but the *write* task may be scheduled first. It yields a few times (`await asyncio.sleep(0)`), which lets its sibling reads reach `acquire()` and register. Only then does it check whether any reads are running. A test lists the write first and checks that it still starts after both reads end.

**Wiring:** `BaseAgent._tool_callbacks()` returns three callbacks that share one scheduler.

- `before_tool`: identity → acquire a slot → confirmation (for writes).
- `after_tool` and `on_tool_error`: release the slot.
  - ADK skips the after-callbacks when a tool raises, so both places must release.
  - Release is idempotent per call id.
- If the turn is cancelled (Stop) while waiting, `before_tool` frees the slot itself.

## Finding 3: the metrics over-counted parallel time

ADK delivers a parallel step's results as **one merged event**. In a live turn with three `fetch_page` calls, each call measured 816 ms, which is the step's wall time. `tool_ms` then *summed* them to 2448 ms, three times more than the user actually waited.

`tool_ms` is now the **union of time intervals**, the time during which at least one tool was running:

- live it reported 834 ms for the same kind of step;
- for sequential steps it still adds up correctly.

Per-call `ms` inside a parallel step still equals the step's time, because ADK doesn't report each tool's own end time.

## Verified

- **93 tests.**
  - The scheduler: reads run concurrently, the cap holds, a write listed first runs after its reads, writes are exclusive, a late read waits, release is idempotent, cancelling frees the slot.
  - The callbacks apply the barrier.
  - The guard test.
  - The interval-union metric.
- **Benchmarks** against real MCP servers, in the tables above.
- **Live:** three `fetch_page` calls in one step took 834 ms in total.
- **Full evals:** routing 1.0, tools 1.0, answers 1.0.

## Lessons

- "Async" is a property of the *whole call chain*. One synchronous call anywhere in it serializes everything sharing that event loop.
- Measure the system before adding parallelism. Here the parallelism existed; it was silently being defeated.
- Concurrency without ordering rules is a bug generator. Decide what may overlap (reads) and what may not (writes), and write tests that pin the ordering.
