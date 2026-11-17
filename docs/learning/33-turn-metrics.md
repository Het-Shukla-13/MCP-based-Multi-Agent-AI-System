# 33 · Turn metrics and token accounting (`feature/turn-metrics`)

## Why first
Phase F measures before changing anything: prompts, retrieval and compaction (later phases) can only be called *better* against numbers.

## What is recorded
- **`turn_metric`** (one row per chat turn):
  - time to first token (TTFT, the latency users *feel*), total, context assembly, agent time;
  - each tool call (name, duration, success, PII-masked args);
  - input/output tokens, fallback used, error, routed vs explicit.
- **`llm_call`** (one row per LLM call): agents, router *and* background jobs (memory extraction, metadata, profile…), with purpose, model, tokens and duration.
- **API:**
  - `GET /metrics/turns`: recent turns.
  - `GET /metrics/summary?days=7`: p50/p95 latency, error and fallback rates, per-agent counts, per-tool calls/failures/p50, tokens by model and purpose. Cost is $0 (free tiers), but tokens are kept so a paid model's cost could be computed.

## Concepts
- **ContextVar** (`current_turn`) carries the turn's collector through all the async code underneath it, with no parameter threading. Two traps:
  1. **Reset it in `finally`**: all messages on one WebSocket run in the *same* task, so a leftover value would leak into the next turn.
  2. **Thread pools drop it:** `loop.run_in_executor` does **not** copy ContextVars (`asyncio.to_thread` does). Demonstrated: plain → `None`, `copy_context().run` → `'turn-123'`. `get_llm_response_async` now copies the context, so Groq calls made in worker threads are attributed to the right turn.
- **Producer/consumer writer:** `put()` only appends to a thread-safe `queue.SimpleQueue`. One task drains it every 0.5 s and batch-inserts in a single transaction. Nothing on the reply path touches the database for metrics. It's flushed on shutdown and best-effort (a failure is logged, never raised).
- **Percentiles, not averages:** p50 is the typical turn; p95 is "slow but not the worst". Averages hide outliers.
- **Background work attribution:** jobs started during a turn inherit its context, so their LLM calls are stored **with that turn's id** even after the reply: a turn's full cost includes its follow-up memory work.

## Bugs found by the live test (and why we test live)
1. **Model `unknown`:** streamed ADK events often omit `model_version`. Now the caller passes the configured model as a fallback.
2. **Successful tools marked failed:** the check searched the result text for "error", but **every** MCP result contains the key `isError` (even `False`). It now reads the boolean. Lesson: use structured fields, not substring guesses.

## First insights (already useful)
- A Data turn with 2–3 tool calls consumed ~11–17k input tokens: tool results flow back into the prompt.
- One routed turn spent ~4 s on context assembly.

These are the baselines for Phase H (compaction, retrieval).

Tests: 42 passed (redaction, percentiles, event collection, ContextVar through the thread pool, writer, MCP `isError`).
