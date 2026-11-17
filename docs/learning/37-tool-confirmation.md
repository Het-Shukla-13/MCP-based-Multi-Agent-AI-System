# 37 — Tool confirmation (human in the loop)

Branch: `feature/tool-confirmation` (Phase G)

## What it does

Some tools have side effects the user will see: `create_file`, `create_from_template` and `generate_image`. Before any of them runs, the turn pauses and the client gets a `tool_confirmation` event showing:

- the tool and the agent calling it;
- the arguments (identity args removed, long content cut to 1500 chars).

The user answers with one of four decisions:

| Decision | Effect |
|---|---|
| `approve` | the tool runs |
| `approve_all` | runs, and the rest of this turn won't ask again |
| `reject` | tool skipped; the model is told "user declined, don't retry, answer in chat" |
| `revise` + feedback | tool skipped; the model gets the feedback and calls the tool again with new args (asked again) |
| (no answer in 10 min) | `expired` = rejected; the turn moves on |

Read-only tools (search, read_file, analyze_code…) never ask.

## Where

- `app/agent_layer/core/confirmation.py` holds the **policy**:
  - which tools need confirmation;
  - the `Decision` type;
  - the arg preview;
  - what the model is told for each decision.

  It has no idea how the user is reached.
- `app/agent_layer/core/base.py`: the agent's `before_tool_callback`. It is now `async` and *awaits* the confirmer when one is present.
- `app/services/turns/runner.py` holds the **transport**:
  - `_ask()` creates a future, broadcasts `tool_confirmation` and waits on it, with a timeout.
  - `confirm()` resolves that future.
  - The snapshot includes `pending_confirmations`, so a reconnecting client sees the prompt again.
- `app/api/ws.py`: the `{"type": "confirm", ...}` command.

## Key concepts

**The tool callback's return value is the whole trick.** ADK calls `before_tool_callback(tool, args, tool_context)` before every tool:

- Returning `None` runs the tool.
- Returning a dict *skips* the tool and gives that dict to the model **as the tool's result**.

So reject and revise need no special protocol with the model. The model reads `{"status": "rejected", "instruction": "...don't retry..."}` like any other tool output, and reacts the way it would to an error.

**Policy and transport meet through a ContextVar.** The runner sets `current_confirmer` inside the turn's task. The agent callback, which runs deep inside ADK in the same task context, reads it.

- When nobody set it (evals, the HTTP endpoint, tests), there is no human to ask, so the call proceeds exactly as before.
- That's why the eval suite still scores 1.0 without any changes.

**Why not ADK's native `require_confirmation`?** It's a pause/resume protocol: the run *ends* with an `adk_request_confirmation` event, and you resume by sending a FunctionResponse into **the same ADK session**. That fits poorly here:

- Our ADK sessions are throwaway, one per request; our DB is the history.
- A turn may be retried on a fallback model.
- The native version only knows approve/reject.

Because the TurnRunner keeps every turn as a live task, simply *awaiting* inside the callback keeps the turn as one continuous run, with streaming, Stop and heartbeat all still working.

**Capability negotiation (backward compatibility).**

- **The problem:** the current UI doesn't know `tool_confirmation`. If the server always asked, every file request from today's UI would hang for 10 minutes and then be rejected.
- **The fix:** a client opts in per message with `confirm_tools: true`.
- **The general rule:** a server must never wait on a client for a feature the client hasn't said it supports.

**Metrics exclude human time.**

- `confirm_ms` is a new `turn_metric` column.
- It is subtracted from `total_ms`, `agent_ms`, TTFT (the part before the first token) and the specific tool call's `ms`, matched by `function_call_id`.
- p50/p95 therefore keep measuring the *system*. Without this, one slow click would make a tool look 30 s slow.

**Edge cases handled.**

- Stop while waiting: the task is cancelled, and the future dies with it.
- A double answer: the second one returns false and gets an error message.
- `revise` with empty feedback: rejected.
- Several pending confirmations in one turn: each has its own id.
- Timeout: treated as `expired`, which is a rejection.

## Small fix on the way

When a model passed `title="green-tea.md"`, the file came out as `green-tea-md.md`. `file_stem()` now drops a known extension before slugifying, while `"v1.2 release notes"` keeps its dot.

## Verified

- **83 tests.**
  - The callback: approve, read-only tools never asking, no confirmer means proceed, reject/revise as the tool result, the preview.
  - The runner: the round trip, the snapshot during a wait, a double answer, `approve_all`, timeout, Stop while waiting, an unknown decision, opt-in.
  - The collector excludes wait time.
  - The filename fix.
- **Live (real model):**
  - Reject: no file; the model put the notes in the chat and said no file was made.
  - Revise ("name it green-tea.md…"): asked again, then approved; the file is `green-tea.md`. The other half of that feedback, adding a fourth bullet, was not verified; a rough bullet count found no fourth bullet.
  - A legacy client without opt-in: no prompts, and the file was created as before.
- **Evals:** tools suite 10/10, matching the baseline.

## Next (frontend, Phase J)

- An inline approval card: tool, args preview, Approve / Approve all / Reject / Revise with a text box.
- Sending `confirm_tools: true` with each message.
- Rendering `pending_confirmations` from `turn_state` after a reconnect.
