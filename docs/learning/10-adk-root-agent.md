# 10 · Real ADK multi-agent root (`feature/adk-root-agent`)

## Concept: delegation in ADK
An `LlmAgent` with `sub_agents=[...]` automatically gets a built-in tool, `transfer_to_agent(agent_name)`, and ADK lists every sub-agent's **`description`** in the parent's prompt. The parent's model reads the message and *calls the tool*. ADK hands the turn to that sub-agent, which answers. Every ADK `Event` has an **`author`**, the agent that produced it.

```
root (ROUTER_MODEL)           ← routes only, never answers
 ├── general  ┐
 ├── code     │  sub-agents built per request with this user's context
 ├── data     │  disallow_transfer_to_parent/peers = True
 ├── research │  → the chosen agent answers instead of bouncing the request
 ├── document │
 └── image    ┘
```
We verified with an experiment first: "hi there" → `transfer_to_agent{'agent_name': 'general'}`; a Python question → `code`; a CSV question → `data`.

**Before:** a plain Python class made a separate gpt-oss JSON call to pick a name. **After:** routing is native ADK delegation (`agents/root_agent.py`), and `core/selector.py` is deleted.

## The description *is* the routing logic
Each agent class now declares `label` and `description`. ADK shows the description to the router model, so the wording directly controls routing quality. `GET /ws/agents` reads the same registry, so the frontend list and the router can never disagree. Before, there was a separate hard-coded list.

## Cost and quota
- Routed turn = 2 model calls (router + agent).
- Explicit `@agent` = 1 call: the root is skipped.
- `ROUTER_MODEL` (`gemini-3.5-flash-lite`) differs from `AGENT_MODEL` (`gemini-3.1-flash-lite`) because free-tier limits are **per model**, so this spreads usage.
- On a quota error, the whole tree retries with `ROUTER_FALLBACK_MODEL` / `AGENT_FALLBACK_MODEL`.

## Backend @mentions (`core/mentions.py`)
Regex `(?<!\S)@([a-zA-Z_]+)\b`. The **negative lookbehind** `(?<!\S)` means "not preceded by a non-space", so `het@code.dev` doesn't match. Only known agent names count (`@john` is ignored). The stored user message keeps the mention; the agent receives the text without it. A UI pick (`selected_agent`) takes priority.

## Live status events
`RootAgent.run(..., on_status=callback)` emits:
- `{"status":"routing","agent":"root"}`
- `{"status":"working","agent":"code","mode":"routed|explicit|fallback"}`

The WebSocket handler forwards them as `{"type":"agent_status","data":{...}}` before the final `chat` message. The frontend can show "Code agent is working…". A failing callback (closed socket) is caught, so it never breaks the turn.

## Which agent wrote each message
New nullable column `message.agent_name` (migration `3fbaeef50690`), included in `MessageRead`. The frontend can now label old messages correctly instead of using "the current agent".

## Error handling
If all models fail → `AgentExecutionError(agent_name, cause)`. `message_service` then:
- saves a clear assistant reply, so every question has an answer and the history stays consistent;
- returns `error: true` (sent over the WebSocket) so the UI can style it;
- logs the full traceback;
- skips memory extraction for that turn.

Before, the user got a generic socket error and a dangling unanswered message.

## Also fixed
- A loguru log line used `%s` placeholders. Loguru uses `{}`, so it printed a literal `%s`.

## Verified live (WebSocket)
| Message | Status events | Agent |
|---|---|---|
| hi there! | routing → working:general | general |
| write a python prime check | routing → working:code | code |
| now add type hints to it | routing → working:code | **code** (follow-up stays) |
| @research what is pgvector? | working:research (no routing call) | research |
| my email is het@code.dev… | routing → working:general | general (email ≠ mention) |
| (all models broken) | routing | error reply, `error=true` |

Tests: 18 passed (new `tests/test_mentions.py`).
