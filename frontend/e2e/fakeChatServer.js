// A scripted stand-in for the chat WebSocket (page.routeWebSocket): tests decide
// exactly which events the "server" sends and can inspect what the client sent.

export const CHAT_WS = /\/ws\/[0-9a-f-]{36}/;

export function savedMessage(role, content, extra = {}) {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    conversation_id: crypto.randomUUID(),
    user_id: crypto.randomUUID(),
    content,
    role,
    token_count: null,
    agent_name: role === "assistant" ? "general" : null,
    status: "complete",
    created_at: now,
    updated_at: now,
    files: [],
    ...extra,
  };
}

/**
 * Install the fake server. Returns a controller:
 *   received          every JSON command the client sent (latest last)
 *   next(predicate)   resolves with the next received command matching predicate
 *   send(type, data)  push an event to the current connection
 *   drop()            close the current connection like a network failure
 */
export async function fakeChatServer(page, { onConnect } = {}) {
  const state = { socket: null, received: [], waiters: [] };
  await page.routeWebSocket(CHAT_WS, (ws) => {
    state.socket = ws;
    ws.onMessage((raw) => {
      const command = JSON.parse(raw);
      state.received.push(command);
      state.waiters = state.waiters.filter((w) => !(w.predicate(command) && (w.resolve(command), true)));
    });
    if (onConnect) onConnect(ws);
    else ws.send(JSON.stringify({ type: "turn_state", data: { current: null, queued: [] } }));
  });
  return {
    received: state.received,
    next(predicate = () => true) {
      const found = state.received.find((c) => predicate(c) && !c.__seen);
      if (found) {
        found.__seen = true;
        return Promise.resolve(found);
      }
      return new Promise((resolve) => state.waiters.push({ predicate, resolve: (c) => { c.__seen = true; resolve(c); } }));
    },
    send(type, data) {
      state.socket.send(JSON.stringify({ type, data }));
    },
    /** A frame exactly as given (e.g. errors, which carry `detail` at the top level). */
    raw(frame) {
      state.socket.send(JSON.stringify(frame));
    },
    drop() {
      state.socket.close({ code: 1006, reason: "network" });
    },
  };
}
