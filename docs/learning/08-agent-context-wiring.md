# 08 · Memory reaches the agents (`feature/agent-context-wiring`)

## Problem 1: the agent's "memory" was ADK's RAM, not our database
The memory system built a token-limited window of recent messages plus a rolling summary of older ones, and then **dropped the window**: only the summary text reached the agent. The agent's conversation history actually came from ADK's `InMemorySessionService`, which:
- **is lost on restart**: after a server restart the agent forgot the whole chat;
- **was separate per agent**: when routing switched from General to Code, Code had never seen the earlier turns;
- **grew forever**, with no token budget, unlike our STM window.

**Fix: one source of truth.** Every turn, `message_service` builds `history` (role + content) from `unified_memory.messages`, our DB window, already token-limited by `build_smart_history`. It skips the summary pseudo-message (sent separately) and the current user message (sent as the new turn). `BaseAgent` renders it into the system instruction, and ADK gets a **throwaway session per request**: ADK needs a session to run, but stores nothing that matters. Agents are now fully stateless.

## Problem 2: an LLM decided what memory to include
Before every reply, an LLM "context router" decided yes/no for long-term memory, profile, files, related conversations and history. It:
- cost **one extra LLM call per message** (latency + free-tier quota);
- often said "no", so attached-file context was silently dropped;
- contradicted the spec: *"always include recent STM + top-k relevant LTM"*.

**Fix: always retrieve, filter by score.** `build_context_policy()` turns every source on. Relevance is now a **similarity threshold**, a number we can tune and test, instead of a model's opinion:
- `MEMORY_MAX_DISTANCE = 1.1`
- `RELATED_CONVERSATION_MAX_DISTANCE = 1.0`

These are L2 distances between normalized embeddings: 0 = identical, about 1.0 = loosely related, 2 = opposite.

**Engineering lesson:** use an LLM where judgement is needed, and plain code where a rule works. Rules are free, fast, deterministic and unit-testable.

## Problem 3: related conversations built, then dropped
`related_conversations_context` was computed but never put into `AgentContext`. It's now a field and its own instruction section.

## Smaller fixes
- `stm_summary` was read from the *stored* metadata (one turn behind). It now uses the state computed this turn.
- Conversation metadata sent to the agent is filtered to descriptive keys (topics, entities, goals, sentiment, summary hint). Internal state like `stm` and `agent_state` no longer leaks into the prompt.
- Empty instruction sections are omitted, keeping the prompt short.

## Verified live
1. "My dog is Bruno, I'm building a CSV sales analyzer" → **Code** agent
2. "Write a function that loads sales.csv…" → **Code**
3. **Server restarted**
4. "What's my dog's name, what were we building, what did your last code compute?" → **General** agent: *"Bruno… CSV sales analyzer… total revenue"* ✅

Context-routing LLM calls: **0**. Tests: 11 passed, including new `tests/test_agent_context.py` (history order, section rendering, empty sections, per-request agent isolation).
