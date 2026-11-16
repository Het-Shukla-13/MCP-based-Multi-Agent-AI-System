# 26 · Silent session refresh in the UI (`feature/fe-session-refresh`)

## Flow
- Sign-in/register store `access_token`, `refresh_token` and the access expiry time (`setSession`).
- **Any API call that gets 401** → the axios response interceptor calls `/auth/refresh` once, stores the new pair and **replays the original request**. The user notices nothing. `_retried` prevents loops: a second 401 is final.
- **Before opening a WebSocket** → `ensureFreshToken()` refreshes if the access token expires within a minute. A socket handshake can't "retry on 401" like an HTTP call.
- **Sign out** → local tokens cleared, then `/auth/logout` revokes the session on the server.
- Refresh fails (expired, revoked, reused) → session cleared → sign-in screen.

## Single-flight refresh (the important part)
The server rotates refresh tokens and treats a **reused** one as theft (branch 25). If five requests fail with 401 at the same moment and each calls `/auth/refresh`, the second call presents an already-rotated token, and the server ends the session. So `refreshSession()` keeps **one in-flight promise** that all callers share. Verified: 5 parallel calls with a corrupted token → **exactly 1** refresh call, all 5 succeed.

`/auth/refresh` goes through a separate axios instance **without** the interceptors, otherwise a failing refresh would try to refresh itself.

## Testing lessons (two false alarms)
1. "Old refresh token still works after sign-out." Sign-out sends `/auth/logout` in the background, and the test fired its own refresh **before the logout reached the server**. Fix: the test waits for the `/auth/logout` response. Wait on real events, not on the UI having changed.
2. "Access token didn't change after refresh." A JWT is a deterministic signature over its claims. Two tokens for the same user issued **in the same second** are identical. Harmless; a random `jti` claim would make each unique (useful if access tokens ever need individual revocation).

## Verified (Playwright)
Refresh token stored at sign-in → corrupted access token + 5 parallel calls → 1 refresh, all succeed, refresh token rotated → expiring token refreshed before the WebSocket connects → sign-out revokes on the server (old token → 401) and clears storage. No page errors.
