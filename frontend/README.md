# Frontend: Multi-Agent Assistant UI

React 19 + Vite chat client for the [MCP-based Multi-Agent AI System](../README.md). It signs users in, streams replies from six specialised agents over a WebSocket, uploads and previews files, and lets users manage what the assistant remembers about them.

## Features
| Area | What you get |
|---|---|
| **Accounts** | Sign in / register, silent session refresh, server-side sign-out |
| **Chat** | Live streaming replies, live status ("🧭 choosing agent" → "📊 Data Agent → table info…"), per-message agent labels, switch banners |
| **Agents** | Type `@code`, `@data`, … (menu with keyboard navigation), or pin an agent per conversation; *Auto* lets the router decide |
| **Replies** | Markdown with tables, code blocks (copy button), and generated images and files |
| **Files** | Drag-and-drop or picker, instant type/size feedback, processing status; "Reply as PDF / Markdown / CSV / JSON / text" |
| **Conversations** | Rename, delete, export to JSON, import from JSON |
| **Memory** | View, search by meaning, add, edit, deactivate and delete memories; view and prune the derived profile |
| **Resilience** | Automatic WebSocket reconnect (backoff + jitter) with conversation resync |
| **Mobile** | Off-canvas conversation drawer, composer always reachable, touch-friendly |

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
| `npm run test:e2e:fast` | Browser tests without LLM calls (~15 s) |
| `npm run test:e2e` | All browser tests, including real-model chat tests |
| `npm run test:e2e:report` | HTML report with traces/screenshots of failures |

## Project structure
```
src/
├── App.jsx                     auth gate: sign-in screen vs chat; validates the stored session
├── pages/
│   ├── AuthPage.jsx            sign in / create account
│   └── ChatPage.jsx            page state: conversations, messages, uploads, agent pins
├── components/
│   ├── Sidebar.jsx             conversation list + rename/export/delete/import, account
│   ├── ChatWindow.jsx          active-agent bar, drag-and-drop zone
│   ├── MessageList.jsx         messages, agent labels, switch banners, live status
│   ├── MarkdownMessage.jsx     safe Markdown rendering (no raw HTML)
│   ├── MessageInput.jsx        composer: @mentions, agent pin, output format, files
│   └── MemoryPanel.jsx         memory + profile drawer
├── hooks/
│   ├── useConversationSocket.js  WebSocket: streaming, status, reconnect, resync
│   └── useConversationUploads.js upload state
└── lib/
    ├── api.js                  axios client, token refresh, all REST calls
    ├── auth.js                 session storage (access/refresh tokens)
    ├── socket.js               WebSocket URL (token in query)
    ├── agents.js               agent icons/labels/status text
    └── uploads.js              client-side file checks (mirror of backend rules)
e2e/                            Playwright end-to-end tests
```

## How it works

### Sessions
- Sign-in returns a short-lived **access token** (JWT, 60 min) and a long-lived **refresh token** (7 days, rotated on every use).
- Every API call carries `Authorization: Bearer <access token>`.
- On a **401**, the client refreshes **once** and replays the request. Parallel failures **share one refresh** (single-flight): two refreshes would rotate the token twice, and the server treats a reused refresh token as theft and ends the session.
- WebSockets and file links can't send headers, so they carry `?token=`. The socket refreshes the token *before* connecting.
- **Sign out** revokes the refresh token on the server.

### WebSocket protocol
```
connect  /ws/{conversation_id}?token=<access token>
send     {"content", "file_ids", "selected_agent"?, "format"?}
receive  agent_status {status: routing|working|tool, agent, tool?}
         chat_delta   {agent, text}            streamed piece → local draft message
         chat         {user_message, ai_message, active_agent, error}   saved result
```
The streamed draft is replaced by the saved `chat` message (the server's copy is the source of truth). On an unexpected close, the hook reconnects after 1 s, 2 s, 4 s … 15 s (+ jitter), refreshes the token first if the server closed with 1008, and reloads the conversation after reconnecting so replies finished while offline still appear.

### State principles
- **Derive, don't copy:** the active agent comes from the latest reply's `agent_name`, and switch banners from the message list.
- **Latest request wins:** overlapping loads ignore stale responses (out-of-order network replies).
- **Per conversation:** agent pins, drafts and uploads are keyed by conversation id.

## Security notes
- Tokens live in `localStorage`, which any script on the page could read. So the UI **never renders untrusted HTML**: Markdown is rendered by `react-markdown` *without* raw HTML (don't add `rehype-raw`), and there's no `dangerouslySetInnerHTML`. A browser test checks that a reply containing `<script>`/`onerror=` executes nothing.
- File type/size checks in `lib/uploads.js` are **feedback only**; the server validates content (magic bytes) and size.
- Generated-file previews are served by the backend with a strict Content-Security-Policy.

## End-to-end tests
Playwright drives a real browser against the real backend and database (`e2e/`, 15 tests): auth, session refresh, composer, conversations, memory, reconnect, phone layout, and `@llm` chat tests that call the free-tier models.

```bash
npx playwright install chromium   # once
npm run test:e2e:fast             # no LLM calls
npm run test:e2e                  # everything
```
Each test registers a fresh user. Embedding-dependent steps allow for free-tier rate limiting, and `@llm` tests only assert deterministic behaviour (explicit `@agent` mentions, rendering, safety).

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| "blocked by CORS policy" in the console | Usually **not** CORS: a backend **500** (e.g. Docker/Postgres not running) loses its CORS headers. Check the backend log. |
| Status pill stuck on *reconnecting* | Backend not running on `VITE_API_BASE_URL`. |
| Signed out unexpectedly | Refresh token expired (7 days), revoked by sign-out elsewhere, or reuse was detected. |
| Replies slow or "provider failed" | Free-tier model limits / provider load; the backend falls back automatically, so retry shortly. |
| `Cannot find native binding` on build | `node_modules` copied from another machine: `rm -rf node_modules && npm ci`. |
