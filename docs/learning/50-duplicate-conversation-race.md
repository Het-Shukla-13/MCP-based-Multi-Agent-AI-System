# 50 — A one-in-many e2e failure was a real race: duplicate conversation rows

Branch: `fix/duplicate-conversation` (found in the Phase K final check).

**Symptom.** In the final full run, 1 of 50 tests failed: after one "New Chat" click the sidebar had **2** rows. The same spec passed 6/6 when repeated.

**Not dismissed as flaky** (lesson of note 47). From the code, the race is:

1. The page starts loading the conversation list (GET).
2. The user clicks New Chat; the server creates the chat (POST).
3. Under load, the GET is answered **after** the chat exists, so the list already contains it, and that response is applied first.
4. Then the POST response arrives, and the client **prepends** the chat again: two rows, one id.

**Reproduced deterministically** with `page.route`:

- hold every list GET until `route.fetch()` shows the server created the chat;
- hold the POST's *response* until the list has been applied.

The result was 2 rows, every time. Two false starts on the way are worth remembering:

- **Wrong order first:** holding only the GET is harmless, because the late list *replaces* state.
- **Dev StrictMode runs effects twice:** the first GET's response is deliberately ignored by the `isMounted` guard. Holding just "the first GET" held the wrong request. Log what the network actually does before reasoning further.

**Fix (one line):** prepend with `current.filter(c => c.id !== conversation.id)`. The regression test is in `e2e/conversations.spec.js`.

**General rule:** when a local optimistic update and a server fetch can land in either order, make every merge **idempotent by id**.
