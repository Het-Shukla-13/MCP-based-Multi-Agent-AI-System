# 36 — Turn runner: detached, stoppable, queued, recoverable turns

Branch: `feature/turn-runner` (Phase G)

## The problem

The WebSocket handler used to `await` the whole turn inline:

```
receive_text() -> send_message_from_payload(...)  # 5-60 s -> send "chat" -> receive_text()
```

That design caused four problems:

1. **No Stop.** During those seconds the loop could not even *read* a "stop" message.
2. **Fragile.** If the tab closed or the network blipped, the turn died with the socket. The user message was saved, but no reply ever came.
3. **No queue.** A second message had to wait in the socket buffer, and the frontend blocked the input.
4. **Crash = dangling question.** If the process died mid-turn, the conversation ended with an unanswered user message forever.

## The design

```
WebSocket (thin command channel)          TurnRunner (owns the work)
  send  ------------------------------->  submit()  -> chat_turn row (queued)
  stop  ------------------------------->  stop()    -> task.cancel()
  dequeue ----------------------------->  dequeue()
  <- turn_state on connect (replay)        lane per conversation: FIFO + 1 worker task
  <- turn_queued / turn_started /          each turn: own asyncio.Task + own DB session
     agent_status / chat_delta /           heartbeat every 10 s; sweeper every 60 s
     chat / turn_finished / error          broadcast to whoever is connected NOW
```

Files:

- `app/services/turns/runner.py`: `TurnRunner` and `LiveTurn`. This is pure logic; storage and execution are injected.
- `app/services/turns/db.py`: `DbTurnStore` (the `chat_turn` rows) and `ChatTurnExecutor` (the real chat pipeline, plus saving the reply of a stopped turn).
- `app/models/turn.py`: the `ChatTurn` table. `Message.status` is new: `complete | stopped | interrupted`.
- `app/api/ws.py`: the command loop and the `turn_state` replay on connect.
- `app/core/websocket.py`: broadcasting now drops dead sockets instead of raising.

## Key concepts

**Lanes, not one global queue.** The turns of *one* conversation must run in order, because message 2 needs reply 1 in its history. *Different* conversations are independent and run concurrently. So there is one FIFO and one worker task per conversation (a "lane"), and the lane is removed when it goes idle.

**Cancelling a task without cancelling yourself.** The worker runs the turn as a child task and waits with `await asyncio.wait({task})`. It does **not** use `await task`, because awaiting a cancelled task re-raises `CancelledError` in the awaiter, which would kill the whole lane on every Stop. `asyncio.wait` never raises, so afterwards the worker inspects `task.cancelled()`, then `task.exception()`, then `task.result()`.

**Stop keeps the partial answer.** The runner accumulates every `chat_delta` into `turn.draft`. On cancellation, `save_stopped` writes the draft as the assistant message with `status="stopped"`.

- The conversation stays well-formed: every question has an answer.
- The model's next turn sees what was already said.
- The `accepted` event, sent as soon as the user message is saved, gives the runner the `user_message_id` it needs for this.

**Heartbeat + sweeper (a lease).** A running turn writes `heartbeat_at` every 10 s. The sweeper runs on startup and then every 60 s. On startup, nothing can be running, so every `running` row belongs to a dead process:

| Row found | Action |
|---|---|
| running, user message saved, no reply | write an "interrupted" reply; row → `interrupted` |
| running, nothing saved yet | safe to re-run → re-queue |
| running, reply already saved | died during bookkeeping → `done` |
| queued (old process's queue) | re-queue, in order |

On periodic sweeps, the sweeper only touches rows whose heartbeat is stale *and* that this process doesn't own. That is the same rule a multi-worker setup would need.

**Replay is a snapshot, not an event log.** On connect, the server sends `turn_state`: the running turn (status, agent, draft so far) and the queue. A reconnecting client renders that and then follows the live events. A snapshot is simpler than storing and re-sending every event, and it is enough because the final `chat` event is the source of truth.

**Isolation from broken sockets.** Every broadcast is wrapped so that a failing send is logged and never breaks the turn. The dead socket is dropped. This was proven during development by an accidental bug (below).

**Shutdown.** Running turns are cancelled, which saves their partial answers. A `_closing` flag stops lanes from starting the *next* queued turn. Those turns stay `queued` in the DB and resume on the next start.

**Short DB sessions.** The old socket held one request-scoped session for its whole life. That left a transaction open while the user was idle. Now the ownership check uses a short session, and each turn opens its own.

## Protocol (backward-compatible)

- **Client → server:**
  - `{content, file_ids, selected_agent, format, client_id}` with no `type`, or `type: "send"`, queues a turn.
  - `{type: "stop"}` cancels the running turn.
  - `{type: "dequeue", turn_id}` removes a queued turn.
- **Server → client:** `turn_state`, `turn_queued{position}`, `turn_started`, `agent_status`, `chat_delta`, `chat` (unchanged shape plus `turn_id`), `turn_finished{status}`, `error`.
- `client_id` is echoed back, so the frontend can match its optimistic bubble to the real turn.

The old frontend only uses `chat`, `chat_delta`, `agent_status` and `error`, so it keeps working. The develop-fe e2e suite passed 15/15 against this backend.

## How it was verified

- `tests/test_turn_runner.py` has 11 tests using a fake store and executor, so they need no DB and no LLM. They cover:
  - order within a lane;
  - Stop saving the draft, after which the next queued turn still runs;
  - a failure not killing the lane, without leaking internals;
  - the queue limit and dequeue;
  - the snapshot;
  - concurrent conversations;
  - input validation;
  - startup resume;
  - shutdown keeping the queue;
  - a broken broadcast.
- **Live**, against the real server, over a WebSocket:
  - A: Stop mid-stream saved 2289 chars as `stopped`.
  - B: two back-to-back messages were answered FIRST, then SECOND.
  - C: after a disconnect, the reconnect got `turn_state` with 3014 draft chars, and the turn completed.
  - D: after `kill -9` mid-turn and a restart, the row was `interrupted` and the conversation ends with an "interrupted" reply.

## Bug caught live (and why the safety net matters)

`ConnectionManager.send_to_conversation(message, conversation_id)` takes its arguments in the opposite order to the runner's `broadcast(conversation_id, message)`. Every send failed with `unhashable type: 'dict'`. Because broadcasts are isolated, the turns still completed and were saved; only the live view was empty.

A small adapter fixed it. The lessons:

- Passing a bound method across a boundary hides the argument order.
- An adapter with the right signature makes that explicit.

## Limits / next steps

- **Single process.** Lanes live in memory, so this assumes one uvicorn worker. To scale out, run the lanes in a worker process and move broadcasting to Redis pub/sub. The DB rows and the protocol stay the same.
- **`POST /chat/send` (HTTP) still runs inline.** It is not used by the UI, and it isn't queued with the WebSocket turns.
- **Frontend still to come (Phase J):** the Stop button, the queue chips, rendering `turn_state` on reconnect, and a "stopped" badge.
