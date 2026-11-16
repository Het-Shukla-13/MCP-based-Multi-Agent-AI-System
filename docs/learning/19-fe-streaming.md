# 19 · Streaming and live status in the UI (`feature/fe-streaming`)

## Event handling (`hooks/useConversationSocket.js`)
| Server event | UI effect |
|---|---|
| `agent_status` routing | "🧭 Choosing the best agent..." |
| `agent_status` working | "💻 Code Agent is working...", plus a pulsing dot in the header |
| `agent_status` tool | "📊 Data Agent → table info..." |
| `chat_delta` | Appends text to a local **draft** message with a blinking cursor |
| `chat` | Replaces the draft (and the pending user message) with the **saved** messages |

The draft is temporary UI state. The final `chat` event carries the server's saved copy, which is the source of truth.

## Derived state instead of copied state
The old hook kept `activeAgent` and `agentSwitched` in React state and synced them from events and conversation changes with `setState` inside effects. That's the pattern the React lint flags, because it causes extra renders and goes stale.
- **Active agent** = `agent_name` of the latest reply (`useMemo` in ChatPage), falling back to the saved conversation state.
- **Switch banners** are computed from the message list itself (a reply whose agent differs from the previous reply's).
- **Connection state** is stored *with its conversation id*. The value shown is derived: a different conversation means "connecting".

**Rule:** if a value can be computed from data you already have, compute it; don't store a second copy that can drift.

## Per-message agent labels
Before, every assistant message was labelled with the *current* agent, so after a switch all old replies showed the wrong agent. Now each reply shows `message.agent_name`, saved by the backend (branch 10). It's verified to survive a reload.

## Also
- `render`-time variable reassignment inside `.map()` was flagged by the React compiler lint. Switch points are computed in a loop before rendering.
- `messages` is memoized: a fresh `[]` fallback on every render defeats `useMemo` dependencies.
- Error replies (`error: true`) get a red style; `lib/agents.js` holds the shared icons, labels and status text.

## Browser-verified (Playwright)
- Draft length sampled while streaming: 100 → 290 → 575 → 887 → 1243 characters.
- Status sequence "routing → General working"; `@code` skips routing.
- Labels General / Code / General with two correct switch banners, unchanged after reload. No page errors.
