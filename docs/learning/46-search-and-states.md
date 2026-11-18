# 46 — Conversation search (⌘K), skeletons, empty states, drafts, copy

Branches: `fix/quota-503` and `feature/conversation-search` (backend, merged first), then `feature/fe-states-and-search`.

## Backend: quota → 503, not 500

- `EmbeddingQuotaExhausted` (the free tier's daily limit) now maps to **503 + `Retry-After`**, with the provider's delay, through one exception handler in `app/core/errors.py`.
- **Why 503:** a 500 means "bug", and a 4xx means "the client's fault". 503 means a temporary server-side condition, so retry later.
- **Verified live** while the quota was actually exhausted: `POST /memories` returned 503 with `retry-after: 5830`. The UI shows the server's `detail`, so users read "temporarily unavailable" without any frontend change.

## Backend: `GET /conversations/search?q=`

- **Matching:** Postgres full-text search over the user's own messages.
  - `websearch_to_tsquery`: words are AND-ed, `"phrases"` and `-exclusions` work, and odd input never raises.
  - `ts_headline` builds the snippet.
- **Results:** one hit per conversation (`DISTINCT ON`, the best rank), plus **title** substring matches.
  - `%` and `_` are escaped, so "100% off_" is literal.
- **Safe highlighting:** highlights are marked with control characters (`\x01` / `\x02`), never HTML, so the client renders `<mark>` elements without `innerHTML`.
- **Index:** a **GIN expression index** on `to_tsvector('english', content)`. The migration is hand-written, because autogenerate doesn't compare expression indexes reliably.
  - `alembic check` shows no drift.
  - A test proves the planner *can* use the index (with `enable_seqscan=off` on a tiny table).
- **Route order matters:** `/search` is declared before `/{conversation_id}`, or FastAPI parses "search" as a UUID (422).
- **DB tests:** snippets, **per-user isolation** (the same words in another user's chat never appear), stemming ("crashing" finds "crashes"), literal wildcards, odd input.

## Frontend

- **⌘K / Ctrl+K palette** (`SearchPalette`):
  - **ARIA:** `role="dialog"` with `aria-modal`; the input is a **combobox** pointing at a listbox via `aria-activedescendant`. Focus stays in the input, ↑ ↓ move, Enter opens, Esc closes and **returns focus** to where it was.
  - **Requests:** debounced by 200 ms. Each new query **aborts** the previous request (`AbortController`), so a slow old response can't overwrite a newer one.
  - **Before typing:** fewer than 2 characters shows recent conversations.
  - **Opening a hit** scrolls to the **matching message** (centred, briefly highlighted), not to the bottom.
- **Skeleton loaders** replace "Loading…" text in the sidebar and the message list. They shimmer, and are static under reduced motion. They're announced as `role="status"` with `aria-busy`.
- **Empty states:**
  - a welcome screen when nothing is selected (with the search shortcut);
  - **6 starter ideas** in an empty chat, one per kind of agent, which fill the composer and focus it.
- **Drafts per conversation:** the composer text moved up into `ChatPage` (`composerDrafts[conversationId]`), so switching chats no longer loses what you typed.
- **Copy → ✓ Copied** on code blocks and on whole answers. `copyText()` falls back to a textarea + `execCommand`, because **`navigator.clipboard` only exists in secure contexts** (https or localhost); opening the app via a LAN IP over http would throw.

## Bugs found along the way (and how)

1. **Test-helper race:** "wait for an *Imported* toast" returned early when an **earlier** import's toast was still visible. The second import then finished later and switched the selected chat away. The fix is to wait for the *outcome*: the header shows the imported title.
2. **"Latest" button out of sync:** the list scrolled to the search hit, but the state still said "at bottom".
   - **How it was found:** a manual `scroll` event fixed it, so the handler was fine and the timing was not.
   - **The likely cause:** the list is **re-mounted** (skeleton ↔ list), and a freshly mounted element gets **no scroll event** for its initial offset.
   - **The fix:** after every layout pass, re-read the real position on the next animation frame. Same-value `setState` is a no-op, so it's cheap.
   - The remount path wasn't traced step by step; the fix holds whichever path re-mounts the list.
3. **Lint `set-state-in-effect`:** `setState` directly in an effect body causes an extra render. The fix relies on the scroll event or a next-frame callback instead.
4. **Flaky full-suite runs:** these exposed a real backend outage bug, the DB pool being starved by background jobs. See note 47.

## Verified

- Backend: 124 tests pass.
- Frontend: the 5 new e2e tests pass; the full non-LLM suite was **39/39 in 4 of the last 5 runs**, including two from a cold start. One run had a single failure whose details were overwritten before they could be read; worth watching.
- The memory e2e test still needs the embedding quota.
