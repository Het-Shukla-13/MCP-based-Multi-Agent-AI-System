# 03 · Agent isolation and async (`fix/agent-isolation-and-async`)

## Bug 1: shared mutable state leaked data between users
Each agent was created once and shared by every user. On each request, `run()` **overwrote** `self.adk_agent.instruction` with that user's memory, profile and file context, and during fallback it overwrote `self.adk_agent.model`. With two concurrent users, request B could overwrite the instruction after A set it but before A's model call read it, so A's reply was generated with B's private context.

**Lesson:** a shared object must be **stateless**: config only, never per-request data. Per-request data belongs in local variables or in new per-request objects.

**Fix:** `_build_request_agent()` creates a **fresh `LlmAgent` per request** (instruction + model for that request), plus a fresh `Runner`. These are cheap Python objects, so nothing shared is mutated. The only shared object left is `session_service`, which keys history by `(user_id, conversation_id)`.

## Bug 2: a sync call inside async code froze the server
FastAPI runs on **one event loop thread**. `async` code is fast only because every `await` hands the thread back while waiting on I/O. `runner.run()` is a *synchronous* generator, so the thread sat waiting on Gemini and every other user's request, WebSocket message and upload stalled.

**Fix:** `runner.run_async()` with `async for`. While Gemini is thinking, the loop serves other requests.

Rule of thumb: inside `async def`, any network or disk call must be awaited (async library) or pushed to a thread (`run_in_executor`, as `llm_service` already does).

## Bug 3: the agent didn't stay sticky
The router's "previous agent" hint was read from `context.conversation_metadata`, but the memory router often sends `{}` there, so it reset to `general`. Now `previous_agent` is an explicit `AgentContext` field, set from the DB state in `message_service.py`.

## Dead code removed
`agent_layer/__init__.py` created a `RootAgentService` with a **second registry** and an extra `GeneralAgent` whenever anything imported the package. The file `services/root_agent_service.py` was deleted.

## Verified live
- 4 users sent messages concurrently to **one shared agent**, each with a different secret in their profile. All 4 got *their own* secret.
- Heartbeat: a coroutine ticking every 0.1s kept ticking normally (24/24) during the 4 calls, so the event loop wasn't blocked.
- Fallback: a simulated 429 on `gemini-3.1-flash-lite` was answered by `gemini-3.5-flash-lite`.
- Routing: "write a python function" went to `code`, and the follow-up stayed on `code`.
