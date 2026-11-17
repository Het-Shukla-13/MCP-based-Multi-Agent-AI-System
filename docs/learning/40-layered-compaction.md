# 40 — Layered compaction (view-only, cheapest first) + resilient context

Branch: `feature/layered-compaction` (Phase H)

## Measure first: where do the tokens go?

- **Per-call metrics:** a Data turn makes about 7.5 LLM calls.
  - Of those, 4 are agent steps, and **each step re-sends** the system instruction, tool declarations and earlier tool results: 3.2k → 3.4k → 4.1k → 4.3k tokens.
  - About 3.4k of the 16.9k turn tokens are background jobs, which don't add to latency.
- **Tool output inside a turn** adds only about 1k tokens. Compressing it would risk hiding data the model still needs, so that was **deliberately not done**.
- **The real problems were in short-term memory (STM):**
  1. **A synchronous LLM summary on the hot path** whenever messages left the window.
  2. **Re-summarising the same messages every turn.** "Dropped" meant *all* messages outside the window, not only new ones.
  3. **The last 10 messages were kept whatever their size.** One pasted log was re-sent in **every agent step** of every turn.

## The layers (`app/services/memory/compaction.py`)

Cheapest first; stop as soon as the history fits `HISTORY_TOKEN_BUDGET` (2,600 tokens):

| Layer | What | Cost |
|---|---|---|
| L0 | fits → nothing | free |
| L1 | older messages over 350 tokens: collapse code blocks (keep 6 lines), then head + tail | free |
| L2 | drop the oldest (never start on an orphan assistant reply); the rolling summary covers them | free |
| L3 | fold dropped, **not yet summarised** messages into the rolling summary | 1 LLM call, **in the background after the turn** |
| L4 | still too big → cap even the newest messages at 1,200 tokens (head + tail) | free |

- **View-only:** compaction builds `ViewMessage` copies. Assigning `message.content` on a loaded ORM object would mark it dirty, and the next commit would silently **rewrite the stored message**. A test checks that inputs are never modified.
- **Head + tail:** the start usually holds the question or context, and the end holds the conclusion or error, so the middle goes.
- **Summarise once:** a `summarized_until` timestamp in `metadata.stm` marks what the summary covers. The background job only folds in newer dropped messages, and a second run with nothing new makes **no** LLM call.
- The turn sets `pending_summary`. `run_memory_maintenance_pipeline` runs `refresh_rolling_summary` first, wrapped in its own try/except.

## Atomic metadata patches (`crud.patch_conversation_metadata`)

**The lost update:**

1. The turn read `convo_metadata` at the start.
2. Background jobs (summary, topics) wrote their keys.
3. The turn then wrote the **whole** dict back from its old copy, which erased what they had written.

**The fix:** each writer sends only the keys it owns, and Postgres merges them in a single statement.

```sql
-- top level
convo_metadata = <object or {}> || :patch
-- nested
convo_metadata = jsonb_set(<object or {}>, '{stm}', <stm or {}> || :patch)
```

| Writer | Keys it owns |
|---|---|
| Turn (STM) | `last_token_usage`, `pending_summary`, `compaction_layers`, … |
| Turn | `agent_state` |
| Background summary | `rolling_summary`, `summarized_until`, `summary_update_count` |
| Background metadata | `topics`, `entities`, `active_goals`, `sentiment`, `summary_hint` |

A Postgres test runs three writers concurrently, each with its own session, and checks that all three updates survive.

**Bug caught by the live test:** a new conversation stores JSON **`null`**, a jsonb scalar rather than SQL NULL. `COALESCE` doesn't replace it, and `jsonb_set` fails with "cannot set path in scalar". The fix is `CASE WHEN jsonb_typeof(x) = 'object' THEN x ELSE '{}' END`, and the test now covers the `null` case.

## Resilience: context assembly degrades instead of failing

With the daily embedding quota exhausted, **every message in a conversation with files failed**: the file-retrieval query embedding was called before the agent ran.

- **File retrieval:** if the query can't be embedded, fall back to **keyword-only** search (Postgres FTS, no external API). Live, "Which bin holds HX-3127-C?" still found R15-06 with no embeddings at all.
- **Long-term memory search:** an embedding failure logs a warning and the turn runs without memories.

The rule: optional context (memory, files) must never take down the turn.

## Results

- **Benchmark:** 60-message chat containing a 900-line log and two 180-line code answers; the old `build_smart_history` loaded from develop-be.

| | Hot-path latency | History tokens | Messages visible |
|---|---|---|---|
| before | 1,594 ms (LLM call) | **16,428** (budget ignored) | 10 |
| after | **25 ms** | **2,499** | **28** |

  The view is 6.5× smaller, and those tokens are saved on *every agent step*. The agent also sees more of the conversation, because big messages are trimmed instead of crowding out the rest.
- **Live:** a 5-turn chat with an 18k-character log paste.
  - "Which job kept timing out?" → **4471**, read from the trimmed log.
  - "My name and destination?" → **Ana, Lisbon**.
  - STM shows `L1` and 935 tokens.
- **Tests:** 115 passing.
- **Evals:** not re-run, because the daily embedding quota is exhausted and the eval workspace needs embeddings. The harness now **reuses** an ingested workspace when the fixtures and the chunking code are unchanged (keyed by a content hash), so a run costs about 32 query embeddings instead of about 240.

## Known limitation

The background pipeline runs its stages in order. If memory promotion fails (it needs embeddings), the later stages such as topics are skipped. The STM summary stage is isolated, but the others still share one try block.
