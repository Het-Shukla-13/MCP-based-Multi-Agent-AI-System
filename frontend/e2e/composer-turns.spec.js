import { expect, test } from "@playwright/test";
import { fakeChatServer, savedMessage } from "./fakeChatServer";
import { newChat, register, trackPageErrors } from "./helpers";

// Composer <-> turn-runner protocol, against a scripted fake server (no LLM).

const input = (page) => page.getByLabel("Chat message input");

async function startTurn(server, command, { draft = "Partial answer" } = {}) {
  server.send("turn_queued", { turn_id: "t1", client_id: command.client_id, position: 1 });
  server.send("turn_started", { turn_id: "t1", client_id: command.client_id });
  server.send("agent_status", { status: "working", agent: "general", turn_id: "t1" });
  server.send("chat_delta", { agent: "general", text: draft, turn_id: "t1" });
}

test("Stop keeps the partial answer and marks it Stopped", async ({ page }) => {
  const assertNoErrors = trackPageErrors(page);
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);

  await input(page).fill("Write a long essay");
  await page.getByRole("button", { name: "Send" }).click();
  const sent = await server.next((c) => c.content);
  expect(sent.client_id).toBeTruthy(); // every send carries a client_id
  await startTurn(server, sent, { draft: "The first half of the essay" });

  await expect(page.locator(".message--streaming")).toContainText("The first half");
  await page.getByRole("button", { name: "Stop" }).click();
  await server.next((c) => c.type === "stop");

  server.send("chat", {
    turn_id: "t1",
    client_id: sent.client_id,
    user_message: savedMessage("user", "Write a long essay"),
    ai_message: savedMessage("assistant", "The first half of the essay", { status: "stopped" }),
    active_agent: "general",
    agent_switched: false,
    error: false,
  });
  server.send("turn_finished", { turn_id: "t1", client_id: sent.client_id, status: "stopped" });

  const reply = page.locator(".message--assistant").last();
  await expect(reply.locator(".message-badge")).toHaveText("Stopped");
  await expect(reply.locator(".message-body")).toHaveText("The first half of the essay");
  await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(0);
  assertNoErrors();
});

test("typing while a reply streams queues the message; it can be removed or run next", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);

  await input(page).fill("First question");
  await page.getByRole("button", { name: "Send" }).click();
  const first = await server.next((c) => c.content === "First question");
  await startTurn(server, first);

  // The input stays usable; the button now says Queue.
  await input(page).fill("Second question");
  await page.getByRole("button", { name: "Queue", exact: true }).click();
  const second = await server.next((c) => c.content === "Second question");
  server.send("turn_queued", { turn_id: "t2", client_id: second.client_id, position: 1 });
  await input(page).fill("Third question");
  await page.getByRole("button", { name: "Queue", exact: true }).click();
  const third = await server.next((c) => c.content === "Third question");
  server.send("turn_queued", { turn_id: "t3", client_id: third.client_id, position: 2 });

  const chips = page.locator(".composer-queue__item");
  await expect(chips).toHaveCount(2);
  await expect(chips.first()).toContainText("Second question");

  // Remove the third before it starts -> dequeue command with the server's turn id.
  await page.getByRole("button", { name: "Remove queued message 2" }).click();
  expect((await server.next((c) => c.type === "dequeue")).turn_id).toBe("t3");
  server.send("turn_finished", { turn_id: "t3", client_id: third.client_id, status: "stopped" });
  await expect(chips).toHaveCount(1);

  // First reply finishes; the second starts: its chip becomes a message bubble.
  server.send("chat", {
    turn_id: "t1",
    client_id: first.client_id,
    user_message: savedMessage("user", "First question"),
    ai_message: savedMessage("assistant", "First answer"),
    active_agent: "general",
    agent_switched: false,
    error: false,
  });
  server.send("turn_finished", { turn_id: "t1", client_id: first.client_id, status: "done" });
  server.send("turn_started", { turn_id: "t2", client_id: second.client_id });
  await expect(chips).toHaveCount(0);
  await expect(page.locator(".message--user").last()).toContainText("Second question");
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible(); // a reply is running again
});

test("a rejected command (queue full) removes only that chip, the stream continues", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);

  await input(page).fill("Question");
  await page.getByRole("button", { name: "Send" }).click();
  await startTurn(server, await server.next((c) => c.content), { draft: "Still streaming" });

  await input(page).fill("One too many");
  await page.getByRole("button", { name: "Queue", exact: true }).click();
  const rejected = await server.next((c) => c.content === "One too many");
  // Same shape as the backend: a rejected command echoes its type and client_id.
  server.raw({ type: "error", detail: "5 messages are already waiting in this conversation.", command: "send", client_id: rejected.client_id });

  await expect(page.locator(".toast", { hasText: "already waiting" })).toBeVisible();
  await expect(page.locator(".composer-queue__item")).toHaveCount(0);
  await expect(page.locator(".message--streaming")).toContainText("Still streaming"); // untouched
});

test("offline notice while reconnecting; it clears once back", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);

  server.drop();
  await expect(page.locator(".composer-notice")).toContainText("Reconnecting");
  await input(page).fill("typed while offline");
  await expect(page.getByRole("button", { name: "Send" })).toBeDisabled();
  await expect(page.locator(".composer-notice")).toHaveCount(0, { timeout: 15_000 }); // auto-reconnect
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
});

test("streaming follows the bottom only when you're there; otherwise 'Latest' appears", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);

  await input(page).fill("Tell me a lot");
  await page.getByRole("button", { name: "Send" }).click();
  const sent = await server.next((c) => c.content);
  await startTurn(server, sent, { draft: "Line\n\n".repeat(80) });
  const list = page.locator(".message-list");
  await expect.poll(() => list.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(80);

  await list.evaluate((el) => el.scrollTo({ top: 0 })); // the user scrolls up to read
  await expect(page.getByRole("button", { name: "Latest" })).toBeVisible();
  server.send("chat_delta", { agent: "general", text: "More\n\n".repeat(40), turn_id: "t1" });
  await page.waitForTimeout(300);
  expect(await list.evaluate((el) => el.scrollTop)).toBe(0); // not yanked down

  await page.getByRole("button", { name: "Latest" }).click();
  await expect.poll(() => list.evaluate((el) => el.scrollHeight - el.scrollTop - el.clientHeight)).toBeLessThan(80);
  await expect(page.getByRole("button", { name: "Latest" })).toHaveCount(0);
});

test("the input grows with the text, up to a cap", async ({ page }) => {
  await fakeChatServer(page);
  await register(page);
  await newChat(page);
  const box = input(page);
  const oneLine = await box.evaluate((el) => el.offsetHeight);
  await box.fill("line\n".repeat(4));
  expect(await box.evaluate((el) => el.offsetHeight)).toBeGreaterThan(oneLine);
  await box.fill("line\n".repeat(60));
  expect(await box.evaluate((el) => el.offsetHeight)).toBeLessThanOrEqual(222);
});

test("a rejected FIRST message removes its bubble and ends the sending state", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);

  await input(page).fill("This one gets rejected");
  await page.getByRole("button", { name: "Send" }).click();
  const sent = await server.next((c) => c.content);
  await expect(page.getByRole("button", { name: "Stop" })).toBeVisible(); // optimistic: shown as running
  server.raw({ type: "error", detail: "Message is too long (max 20000 characters).", command: "send", client_id: sent.client_id });

  await expect(page.locator(".toast", { hasText: "too long" })).toBeVisible();
  await expect(page.locator(".message--user")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Stop" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
});
