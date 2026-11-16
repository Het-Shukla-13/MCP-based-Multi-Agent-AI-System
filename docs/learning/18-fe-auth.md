# 18 · Frontend auth (`feature/fe-auth`)

## What changed
- **`lib/auth.js`:** token store (`localStorage`) with an `onTokenChange` subscription, so any part of the app (including a 401 from the server) can log the user out everywhere at once.
- **`lib/api.js`** (axios):
  - a **request interceptor** adds `Authorization: Bearer <token>` to every call;
  - a **response interceptor** turns any 401 into a logout.
  - Removed every `user_id` parameter: the backend takes identity from the token.
- **WebSocket / file links:** the browser can't add headers to `new WebSocket()`, `<a href>` or `<img src>`, so `?token=` is added (`buildConversationWebSocketUrl`, `withToken`, `generatedFileUrl`).
- **`AuthPage`:** sign in / create account. The browser's built-in validation (`type="email"`, `minLength=8`) runs before any request.
- **`App`:** no token → AuthPage. Token → `GET /auth/me` validates it (it may be expired or forged) → ChatPage. `key={user.id}`, so switching accounts gives completely fresh state.
- Sidebar shows the account email and a **Sign out** button.

## Bugs fixed on the way
- `import Sidebar from "../components/SideBar"` while the file is `Sidebar.jsx`: it works on macOS (case-insensitive filesystem) but **breaks the build on Linux/CI**. Renamed properly.
- The selected agent was kept in **global localStorage**, so one `@pick` silently disabled routing in every conversation. It's now component state.
- Removed the dead `useFileGeneration` hook (it imported functions that no longer existed) and the duplicate `AgentSwitcher` badge.
- `VITE_USER_ID` (a hard-coded user in config) is gone. `.env.example` documents `VITE_API_BASE_URL`.

## Token storage trade-off
- `localStorage` is simple and survives reloads, but **any script on the page can read it**. So the app must never inject untrusted HTML (next branches render Markdown without raw HTML).
- An `httpOnly` cookie would hide the token from scripts but requires CSRF protection. Both are valid; the important part is knowing which risk you accepted.

## Debugging lesson: "CORS error" that wasn't CORS
The first browser test failed with *"blocked by CORS policy"*. The real cause was in the backend log: `POST /auth/register → 500`, because **Docker had stopped, so Postgres refused connections**. Unhandled 500 responses skip the CORS middleware, so the browser hides the real error behind a CORS message. **Always check the server log before believing a CORS error.**

## Tested in a real browser (Playwright, outside the repo)
Short password blocked by browser validation → register → chat page shows the email → WebSocket connected → reply "pong" → sign out clears the token → wrong password shows "Incorrect email or password" → sign in restores the conversations → forged stored token → automatic logout. **No page errors.**
