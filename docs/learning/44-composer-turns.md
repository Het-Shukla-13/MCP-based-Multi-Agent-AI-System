# 44 — Composer ↔ turn runner: Stop, queue, offline, scroll, auto-grow

Branch: `feature/fe-composer-turns` (Phase J). The name `feature/fe-composer` was already taken by the older composer branch; branches are never deleted, so this one got a new name.

This branch connects the UI to the server-owned turns from note 36.

## Protocol used

- **Sending:** every send carries a `client_id` (a UUID). The server echoes it on every event of that turn: `turn_queued`, `turn_started`, `chat`, `turn_finished`, `error`.
- **Commands:**
  - `{type: "stop"}` stops the running reply; the server keeps the partial answer as a `stopped` message.
  - `{type: "dequeue", turn_id}` removes a queued message.
- **Replay:** on connect, `turn_state.queued` restores the queue.

## Behaviour

| Situation | UI |
|---|---|
| Idle, you send | an optimistic "Sending…" bubble; Stop appears |
| A reply is running, you type | the input stays usable; **Send → "Queue"**; the message becomes a chip "Queued 1" |
| ✕ on a chip | `dequeue` with the server's `turn_id`; `turn_finished(stopped)` removes the chip |
| The running reply finishes and the next starts | `turn_started(client_id)` moves the chip into the conversation as a bubble |
| Stop | partial answer saved; the reply shows a **Stopped** badge (the crash sweeper's replies show **Interrupted**) |
| Stopped before the question was saved | no `chat` event, so `turn_finished` removes the bubble |
| Offline / reconnecting | a notice "Connection lost. Reconnecting… You can keep typing."; Send disabled until back |

## Errors: two different things

- **`error` with a `turn_id`:** that turn failed. Drop its bubble and the draft, and end the turn.
- **`error` without a `turn_id`:** a **rejected command**, such as "queue full", "message too long" or "nothing to stop". The reply currently streaming is fine and must not be touched (the old handler wiped it).
  - The client keeps `unconfirmedRef`, the client ids sent but not yet confirmed by `turn_queued` or `turn_started`, and undoes only the newest of them.
  - If that send was a queued chip, only the chip is removed.
  - If not, it was the optimistic running bubble: the bubble is removed and the sending state ends.

## The React bug the tests caught: reading values out of updaters

```js
let started = null;
setQueue(cur => { started = cur.items.find(...); return ...; });
updateMessages(msgs => ... started ...);   // started is still null here
```

**Functional state updaters don't run when you call them.** React queues them and runs them during the next render, **in hook declaration order**, not in call order. Here the messages state is declared before the queue state, so its updater ran first and saw `null`. StrictMode also runs updaters twice on purpose, so side effects inside them are unsafe anyway.

**The fix:** a ref is the synchronous source of truth, and state only re-renders.

```js
const writeQueue = (conversationId, compute) => {
  const items = queueRef.current...;          // read now
  queueRef.current = { conversationId, items: compute(items) };
  setQueue(queueRef.current);                  // plain value, no updater
  return items;                                // previous items, for the caller
};
```

## Scrolling

- **Before:** `scrollIntoView({behavior: "smooth"})` on every update, which **yanked** you down while you were reading older messages, and lagged behind fast streams.
- **After:** follow new content only while you're within 80px of the bottom, or right after you send, or when you open a conversation.
  - It jumps instantly (`scrollTop = scrollHeight`), inside a `useLayoutEffect` so there's no flicker before paint.
  - When you've scrolled up, a floating **"↓ Latest"** button appears.
  - The button's visibility is updated from the scroll handler, not from an effect.

## Auto-growing input

`useLayoutEffect` on the text: set `height = "auto"`, then `height = min(scrollHeight, 220px)`. Beyond that the textarea scrolls. It starts at one row, and the manual resize handle is removed.

## Tests: `e2e/composer-turns.spec.js` with `e2e/fakeChatServer.js`

`fakeChatServer` is a reusable scripted server (`page.routeWebSocket`):

- `next(predicate)` waits for a command from the client;
- `send` pushes an event;
- `raw` sends a frame exactly as given (errors carry `detail` at the top level, like the backend);
- `drop` simulates a network failure.

**Seven deterministic tests:**

1. Stop keeps the partial answer and shows the Stopped badge.
2. Queue: a chip appears, it can be removed (`dequeue` with the right `turn_id`), and the next message starts.
3. A rejected command doesn't touch the stream.
4. A rejected **first** message removes its bubble.
5. The offline notice appears, Send is disabled, then it auto-recovers.
6. Scroll follows only at the bottom; "Latest" appears and works.
7. Auto-grow respects the cap.

**Playwright detail:** role names match as a case-insensitive **substring** by default. `name: "Queue"` also matched "Remove queued message 1", hence `exact: true`.

## Verified

- The fast suite: 21/22 pass. The memory test is still blocked only by the embedding quota.
- The visual spec passes; lint and build are clean.
