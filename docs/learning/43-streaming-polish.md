# 43 — Streaming polish: frame-batched deltas, a live step checklist, replay

Branch: `feature/fe-streaming-polish` (Phase J)

## 1. Batch deltas to one render per frame

- **Before:** every `chat_delta` (one per streamed chunk, often dozens per second) called `setMessagesByConversation`, which re-rendered the message list and re-parsed the draft's Markdown **per token**.
- **After:** inside the socket effect, deltas go into a buffer, `{ text, agent }`, and a `requestAnimationFrame` flush applies them with **one** state update, so there is at most one render per frame however fast tokens arrive.

```js
buffered.text += data.text;
if (!frame) frame = requestAnimationFrame(flush);
```

- **Flush before anything that depends on the text:** the final `chat` and `error` events call `flushNow()` first. Otherwise the saved message could land while text is still in the buffer.
- **Background tabs:** `requestAnimationFrame` pauses in hidden tabs. Text just accumulates and is applied once, which is cheaper, and `chat` still flushes it.
- **Cleanup:** the pending frame is cancelled when the conversation closes.
- **Test:** the fake server sends **300 one-character deltas back to back**, and the draft must equal the full text in order.

## 2. A live checklist instead of one overwritten status line

- **Pure reducer** in `src/lib/turnProgress.js` (no React): `progressReducer(state, agent_status)`.
  - Steps are `routing → agent → tool… → writing`.
  - The server only reports when a step **starts**, so a step is marked done when the next one starts or the turn ends. That's the usual inference.
  - Duplicate events don't add a step.
- **`waiting`** (the backend's rate-limit wait, from note 40) isn't a step. It's a pause on the current one, shown as a **countdown**: "The AI provider is rate-limiting us. Retrying in 12s…".
- **`ThinkingIndicator`:**
  - a spinner on the active step and a check on finished ones;
  - before any text, a full card at the bottom;
  - once text streams, it collapses into a **compact row of chips** above the draft.
- **Accessibility:** a single visually-hidden `role="status"` announces only the **current** step. Announcing the whole list on every change would be noise. The visual list is `aria-hidden`.

## 3. Replay after reconnect or refresh (uses the turn-runner, note 36)

- On connect, the server sends `turn_state` with `{status, agent, draft}` for a running turn.
- The client restores the draft, marks the conversation as sending, and rebuilds an approximate checklist with `progressFromSnapshot`.

**A race the test found:** opening a conversation fetches its saved messages and used to **replace** the whole list, which can wipe a draft that `turn_state` has just restored. In real life that happens when you refresh the page mid-reply.

The fix: one helper, `withLocalMessages(saved, current)`, which keeps the local draft and pending messages. Both the initial load and the post-reconnect resync use it.

## 4. Caret

- **Before:** the caret was a separate `<span>` *after* the Markdown block, so it showed on its own line under the text.
- **After:** a `::after` pseudo-element on the **last block** of a `.message--streaming` message, so it sits at the end of the last line. It is a thin accent bar that blinks, and is steady under `prefers-reduced-motion`.
- The e2e helper now waits for `.message--streaming` to disappear.

## Deterministic streaming tests (`e2e/streaming.spec.js`)

`page.routeWebSocket(CHAT_WS, ws => …)` makes the test **be** the chat server: no LLM, no quota, exact timing.

1. **The full turn:**
   - the checklist steps appear, and earlier ones are ticked;
   - the countdown is visible;
   - the test releases the wait;
   - 300 batched deltas arrive complete and in order;
   - the saved message replaces the draft, and the indicator goes away.
2. **Replay:** a connection that opens mid-reply shows the draft and "Writing the answer". The stream then continues and finishes.

## Verified

- The fast suite passes 14/15. The memory test is still blocked only by the embedding quota.
- The visual spec passes, and lint and build are clean.
