import { expect, test } from "@playwright/test";
import { newChat, register, trackPageErrors } from "./helpers";

// Deterministic streaming tests: the chat WebSocket is answered by a scripted fake
// server (page.routeWebSocket), so no LLM, no quota and exact timing control.

const CHAT_WS = /\/ws\/[0-9a-f-]{36}/;
const LONG_ANSWER = "Lisbon in May is warm and bright. ".repeat(9).trim(); // ~300 chars

function savedMessage(role, content, extra = {}) {
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

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

test("live checklist, rate-limit countdown, batched deltas, then the saved reply", async ({ page }) => {
  const assertNoErrors = trackPageErrors(page);
  let release; // the test decides when the fake server continues past the "waiting" step
  const proceed = new Promise((resolve) => (release = resolve));

  await page.routeWebSocket(CHAT_WS, (ws) => {
    const send = (type, data) => ws.send(JSON.stringify({ type, data }));
    send("turn_state", { current: null, queued: [] });
    ws.onMessage(async (raw) => {
      const { content } = JSON.parse(raw);
      send("agent_status", { status: "routing", agent: "root" });
      await wait(150);
      send("agent_status", { status: "working", agent: "general", mode: "routed" });
      await wait(150);
      send("agent_status", { status: "tool", agent: "general", tool: "web_search" });
      await wait(150);
      send("agent_status", { status: "waiting", agent: "general", seconds: 2 });
      await proceed;
      // 300 one-character deltas, back to back: batching must not lose or reorder any.
      for (const ch of LONG_ANSWER) send("chat_delta", { agent: "general", text: ch });
      await wait(400);
      send("chat", {
        user_message: savedMessage("user", content),
        ai_message: savedMessage("assistant", LONG_ANSWER),
        active_agent: "general",
        agent_switched: false,
        error: false,
      });
    });
  });

  await register(page);
  await newChat(page);
  await page.getByLabel("Chat message input").fill("Is May a good time for Lisbon?");
  await page.getByRole("button", { name: "Send" }).click();

  const thinking = page.locator(".thinking");
  await expect(thinking).toContainText("Choosing the best agent");
  await expect(thinking).toContainText("General Assistant is on it");
  await expect(thinking).toContainText("Using web search");
  // Earlier steps are ticked off as later ones start.
  await expect(thinking.locator(".thinking__step--done")).toHaveCount(2);
  await expect(page.locator(".thinking__waiting")).toContainText(/Retrying in [12]s/);

  release();
  const draft = page.locator(".message--streaming");
  await expect(draft).toBeVisible();
  await expect(page.locator(".thinking--compact")).toContainText("Writing the answer");
  await expect(draft.locator(".message-body")).toHaveText(LONG_ANSWER); // every delta, in order

  // The saved message replaces the draft; the indicator goes away.
  await expect(page.locator(".message--streaming")).toHaveCount(0);
  await expect(page.locator(".thinking")).toHaveCount(0);
  await expect(page.locator(".message--assistant .message-body").last()).toHaveText(LONG_ANSWER);
  assertNoErrors();
});

test("reconnecting mid-reply replays the draft and the current step", async ({ page }) => {
  let server;
  await page.routeWebSocket(CHAT_WS, (ws) => {
    server = ws;
    // The server says a reply is already being written for this conversation.
    ws.send(JSON.stringify({
      type: "turn_state",
      data: { current: { status: "running", agent: "general", draft: "Half of the answer" }, queued: [] },
    }));
  });

  await register(page);
  await newChat(page);

  const draft = page.locator(".message--streaming");
  await expect(draft.locator(".message-body")).toHaveText("Half of the answer");
  await expect(page.locator(".thinking--compact")).toContainText("Writing the answer");

  // Streaming continues where it left off, then the saved reply lands.
  server.send(JSON.stringify({ type: "chat_delta", data: { agent: "general", text: " and the rest." } }));
  await expect(draft.locator(".message-body")).toHaveText("Half of the answer and the rest.");
  server.send(JSON.stringify({
    type: "chat",
    data: {
      user_message: savedMessage("user", "earlier question"),
      ai_message: savedMessage("assistant", "Half of the answer and the rest."),
      active_agent: "general",
      agent_switched: false,
      error: false,
    },
  }));
  await expect(page.locator(".message--streaming")).toHaveCount(0);
  await expect(page.locator(".message--assistant .message-body").last()).toHaveText("Half of the answer and the rest.");
});
