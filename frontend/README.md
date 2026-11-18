# Frontend: Multi-Agent Assistant UI

React 19 + Vite chat client for the [MCP-based Multi-Agent AI System](../README.md). It signs users in, streams replies from six specialised agents over a WebSocket, lets users stop, queue and approve what the agents do, uploads and previews files, searches past conversations, and shows what the assistant remembers and how much it is being used.

## Features
| Area | What you get |
|---|---|
| **Accounts** | Sign in / register, silent session refresh, server-side sign-out |
| **Chat** | Smooth streaming (rendered once per frame), a live step checklist ("Choosing the best agent" ✓ → "Data Agent" ✓ → "Using table info" → "Writing the answer"), a rate-limit countdown, per-message agent labels |
| **Control** | **Stop** keeps the partial answer (marked *Stopped*); typing while a reply runs **queues** messages as removable chips; a refresh mid-reply restores the half-written answer |
| **Approvals** | Before an agent creates a file or image: a card showing what it will create, with **Approve · Approve all · Revise (with feedback) · Reject** and an expiry countdown |
| **Agents** | Type `@code`, `@data`, … (keyboard menu), or pin an agent per conversation; *Auto* lets the router decide |
| **Replies** | Document-style Markdown (tables, code with Copy → ✓, images, generated files); copy a whole answer |
| **Files** | Drag-and-drop or picker, instant type/size feedback, processing status; "Reply as PDF / Markdown / CSV / JSON / text" |
| **Search** | **⌘K / Ctrl+K** searches what was said in your chats (full-text), highlights matches and opens the conversation at the matching message |
| **Conversations** | Rename, delete, export/import JSON; unsent drafts kept per chat; starter ideas in an empty chat |
| **Memory** | View, search by meaning, add, edit, deactivate and delete memories; view and prune the derived profile |
| **Usage** | Replies, typical reply time (p50/p95), time to first words, tokens by model and purpose, tools, recent replies; 7/30/90 days |
| **Look** | Warm light and dark themes (Auto/Light/Dark, no flash on load), Inter, design tokens, one focus ring, reduced-motion support |
| **Resilience** | Auto-reconnect (backoff + jitter) with resync; offline notice; toasts instead of a blocking banner |
| **Mobile** | Off-canvas drawer, composer always reachable, full-screen panels, no horizontal overflow |

## Quick start
Prerequisites: Node 20+, and the backend running (see the [root README](../README.md): `docker compose up -d`, then the API on `http://127.0.0.1:8000`).

```bash
cd frontend
# Optional: cp .env.example .env  only if the backend is NOT on http://127.0.0.1:8000.
# Never put secrets here: VITE_* values are baked into the JavaScript sent to browsers.
npm ci
npm run dev                 # http://localhost:5173
```
Create an account on the sign-in screen. There are no preconfigured users.

| Script | Purpose |
|---|---|
| `npm run dev` | Dev server with hot reload |
| `npm run build` / `npm run preview` | Production build / serve the build |
| `npm run lint` | ESLint (React hooks + compiler rules) |
| `npm run test:e2e:fast` | Browser tests without LLM calls |
| `npm run test:e2e` | All browser tests, including real-model chat tests |
| `npm run test:visual` | Screenshots of key screens (both themes, desktop + phone) into `test-results/visual/` |
| `npm run test:e2e:report` | HTML report with traces/screenshots of failures |
| `python3 scripts/check-contrast.py` | WCAG AA contrast of every text/background token pair, both themes |

## Project structure
```
src/
├── App.jsx                     auth gate: sign-in screen vs chat; validates the stored session
├── tokens.css                  design tokens: scales + semantic colours, light/dark
├── styles.css                  components (tokens only, no raw colours)
├── pages/
│   ├── AuthPage.jsx            sign in / create account
│   └── ChatPage.jsx            page state: conversations, messages, drafts, uploads, panels
├── components/
│   ├── Sidebar.jsx             conversations (+ skeletons), search button, account, theme
│   ├── ChatWindow.jsx          active-agent bar, drag-and-drop zone
│   ├── MessageList.jsx         messages, follow-the-bottom scrolling, "Latest", empty states
│   ├── ThinkingIndicator.jsx   live step checklist + rate-limit countdown
│   ├── ConfirmationCard.jsx    approve / approve all / revise / reject a tool call
│   ├── MessageInput.jsx        composer: auto-grow, Stop, queue chips, offline notice, @mentions
│   ├── MarkdownMessage.jsx     safe Markdown rendering (no raw HTML), copy buttons
│   ├── SearchPalette.jsx       ⌘K conversation search (combobox dialog)
│   ├── MemoryPanel.jsx         memory + profile drawer
│   ├── usage/                  usage panel, column chart, ranked bars
│   ├── Toaster.jsx             toasts (polite / assertive live regions)
│   └── ThemeToggle.jsx         Auto / Light / Dark
├── hooks/
│   ├── useConversationSocket.js  WebSocket: turns, streaming, queue, stop, approvals, replay
│   ├── useConversationUploads.js upload state
│   ├── useToasts.js / useCopy.js / useElementWidth.js
└── lib/
    ├── api.js                  axios client, token refresh, all REST calls
    ├── auth.js                 session storage (access/refresh tokens)
    ├── socket.js               WebSocket URL (token in query)
    ├── turnProgress.js         pure reducer: status events -> step checklist
    ├── theme.js                theme preference (+ inline no-flash script in index.html)
    ├── clipboard.js            copy with a fallback outside secure contexts
    ├── agents.js               agent icons/labels/status text
    └── uploads.js              client-side file checks (mirror of backend rules)
e2e/                            Playwright tests (+ fakeChatServer.js, usageFixture.js)
```

## How it works

### Sessions
- Sign-in returns a short-lived **access token** (JWT, 60 min) and a long-lived **refresh token** (7 days, rotated on every use).
- Every API call carries `Authorization: Bearer <access token>`.
- On a **401**, the client refreshes **once** and replays the request. Parallel failures **share one refresh** (single-flight): two refreshes would rotate the token twice, and the server treats a reused refresh token as theft and ends the session.
- WebSockets and file links can't send headers, so they carry `?token=`. The socket refreshes the token *before* connecting.
- **Sign out** revokes the refresh token on the server.

### Turns over the WebSocket
The full protocol is in the [root README](../README.md#websocket-protocol). The client side works like this:

- **Every send has a `client_id`.** The server echoes it on every event of that turn: `turn_queued`, `turn_started`, `chat`, `turn_finished`, `error`.
- **When idle,** a send shows an optimistic bubble.
- **While a reply runs,** a send becomes a **queued chip**. `turn_started` moves the chip into the conversation, and ✕ sends `dequeue`.
- **Streamed text** (`chat_delta`) is buffered and applied **once per animation frame**. The saved `chat` message then replaces the draft.
- **`stop`** keeps the partial answer.
- **`turn_finished`** closes turns that end without a `chat` event, such as one stopped before the question was saved.
- **Errors carry `command`** when a *command* was rejected (queue full, stale approval). Only that command is undone, and a streaming reply is never touched.
- **On (re)connect,** `turn_state` restores a running draft, its step, queued chips and pending approvals. Saved messages are **merged** with it, never replacing it.
- **Reconnection** uses backoff of 1 s, 2 s, 4 s … 15 s (+ jitter), and refreshes the token first if the server closed with 1008.

### State principles
- **Derive, don't copy:** the active agent comes from the latest reply's `agent_name`, and switch banners from the message list.
- **Latest request wins:** overlapping loads ignore stale responses, and search aborts the previous request (`AbortController`).
- **Read synchronously from refs, not from `setState` updaters:** React runs updaters later, during render and in hook order. The queue lives in a ref for that reason.
- **Per conversation:** agent pins, drafts, uploads and queues are keyed by conversation id.

## Security notes
- Tokens live in `localStorage`, which any script on the page could read. So the UI **never renders untrusted HTML**:
  - Markdown is rendered by `react-markdown` *without* raw HTML (don't add `rehype-raw`);
  - search highlights are built from control-character markers, not HTML;
  - there's no `dangerouslySetInnerHTML`.
  - A browser test checks that a reply containing `<script>`/`onerror=` executes nothing.
- File type/size checks in `lib/uploads.js` are **feedback only**; the server validates content (magic bytes) and size.
- Generated-file previews are served by the backend with a strict Content-Security-Policy.

## End-to-end tests
Playwright drives a real browser against the real backend and database (`e2e/`, 50 tests). Each test registers a fresh user.

- **Fast (no LLM):**
  - auth and sessions, conversations, memory, search, usage, reconnect, phone layout;
  - streaming, queue, Stop and approvals, tested against **`fakeChatServer.js`**, a scripted WebSocket server (`page.routeWebSocket`), so timing and events are exact and free.
- **`@llm`:** real-model chat tests that only assert deterministic behaviour (labels, rendering, safety).
- **Visual:** `npm run test:visual` saves screenshots; it includes a no-horizontal-overflow check on phones.

```bash
npx playwright install chromium   # once
# Run the backend with background LLM jobs off, so test runs don't spend the daily
# free-tier token budget:  BACKGROUND_LLM_JOBS_ENABLED=false .venv/bin/uvicorn main:app --port 8000
npm run test:e2e:fast             # no LLM calls
npm run test:e2e                  # everything
```

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| "blocked by CORS policy" in the console | Usually **not** CORS: a backend **500** (e.g. Docker/Postgres not running) loses its CORS headers. Check the backend log. |
| Status pill stuck on *reconnecting* | Backend not running on `VITE_API_BASE_URL`. |
| Signed out unexpectedly | Refresh token expired (7 days), revoked by sign-out elsewhere, or reuse was detected. |
| "temporarily unavailable" when adding a memory or uploading | The free-tier embedding quota for the day is used up (the API returns 503 + Retry-After). Chat still works. |
| Replies slow, or a "rate-limiting us" countdown | Free-tier model limits; the backend waits briefly or falls back automatically. |
| `Cannot find native binding` on build | `node_modules` copied from another machine: `rm -rf node_modules && npm ci`. |
