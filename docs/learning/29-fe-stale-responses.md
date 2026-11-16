# 29 · Out-of-order responses in the memory panel (`fix/fe-stale-responses`)

**Found by:** the committed e2e suite running in parallel (note 30). It passed alone and failed under load.

**Symptom:** after deactivating a memory and ticking "show inactive", the list said "No memories yet", although the memory existed.

**Cause: a stale-response race.**
1. Deactivate → reload the list (active only) → request **A**
2. Tick "show inactive" → reload (including inactive) → request **B**
3. Under load **B returns first** (list shows the memory), then **A returns and overwrites** it with its older, empty result.

It's invisible on a fast local machine and real for users on slow networks or a busy server.

**Fix:** each load takes an increasing request id (kept in a `useRef`). When a response arrives it updates state **only if it belongs to the latest request**. Applied to both the memory list and the profile tab. (ChatPage's loads already guard with per-effect cleanup flags.) Alternatives: `AbortController` to cancel the older request, or a data-fetching library that handles it.

**Lesson:** "last request wins" is not automatic. Responses arrive in network order, not request order. Any UI that can fire overlapping requests for the same state needs this guard.
