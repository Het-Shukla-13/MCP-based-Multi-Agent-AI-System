# 27 · WebSocket auto-reconnect (`feature/fe-ws-reconnect`)

## Behaviour
| Event | What happens |
|---|---|
| Unexpected close (server restart, network drop) | Pill shows **reconnecting**; retries after 1s, 2s, 4s, 8s, then every 15s (+ up to 30% jitter) |
| Close code **1008** (server rejected auth) | Refresh the token first, then reconnect |
| Browser fires `online` | Reconnect immediately (skip the remaining backoff) |
| Reconnected | Drop any half-streamed draft and **reload the conversation** (`onResync`) |
| User switches chat / signs out | `stopped` flag: no reconnect for a socket we closed on purpose |

## Concepts
- **Exponential backoff:** each failure doubles the wait, so a down server isn't hammered with retries.
- **Jitter:** a random extra delay. Without it, every browser that lost the same server reconnects at the *same* instant when it comes back (the "thundering herd").
- **Resync after reconnect:** the server keeps working on a reply after the socket drops and saves it. Reloading messages after reconnecting makes sure the user sees it. (Our server also broadcasts a conversation's events to every open socket for that conversation, so the reply can also arrive live on the new socket. Both paths lead to the same saved message.)
- `onerror` is always followed by `onclose`, so reconnection lives in `onclose` only.
- `onResync` is kept in a ref, so a new callback identity doesn't tear down and re-open the socket.

## Testing lessons
- **Chromium's offline emulation doesn't close already-open WebSockets**, so "go offline" didn't simulate a drop. The test injects a tiny init script that records sockets, then calls `close()` on the live one, which is a real drop.
- Right after `close()` the UI still says "connected" (the close event is asynchronous). Wait for the **new state** ("reconnecting", then a new socket in OPEN state), not for a state that was already true.

## Verified (Playwright)
- **A:** backend killed for 8 s → pill "reconnecting" → back automatically ("Reconnected.").
- **B:** socket dropped mid-reply → "reconnecting" → new socket → full reply shown (1337 chars), no stuck pending message. No page errors.
