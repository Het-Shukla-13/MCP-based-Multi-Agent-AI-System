import { expect, test } from "@playwright/test";
import { fakeChatServer } from "./fakeChatServer";
import { newChat, register, trackPageErrors } from "./helpers";

// Tool-confirmation UI against a scripted fake server (no LLM).

const input = (page) => page.getByLabel("Chat message input");

const FILE_REQUEST = {
  confirmation_id: "k1",
  agent: "document",
  tool: "create_file",
  args: { title: "green-tea.md", file_format: "md", content: "- antioxidants\n- calm focus" },
  timeout_seconds: 600,
};

async function runningTurn(page, server) {
  await input(page).fill("Make me a file about green tea");
  await page.getByRole("button", { name: "Send" }).click();
  const sent = await server.next((c) => c.content);
  server.send("turn_started", { turn_id: "t1", client_id: sent.client_id });
  server.send("agent_status", { status: "working", agent: "document" });
  server.send("agent_status", { status: "tool", agent: "document", tool: "create_file" });
  return sent;
}

test("approve: the card shows what will be created, the decision is sent, the card clears", async ({ page }) => {
  const assertNoErrors = trackPageErrors(page);
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);
  const sent = await runningTurn(page, server);
  expect(sent.confirm_tools).toBe(true); // this client can answer confirmations

  server.send("tool_confirmation", FILE_REQUEST);
  const card = page.getByRole("region", { name: "Approval needed: Create a file" });
  await expect(card).toContainText("Document Agent wants to create a file");
  await expect(card).toContainText("green-tea.md");
  await expect(card).toContainText(".md");
  await expect(card).toContainText(/expires in 9:5\d|expires in 10:00/);
  await card.getByText("Preview content").click();
  await expect(card.locator("pre")).toContainText("calm focus");
  await expect(page.locator(".thinking")).toContainText("Waiting for your approval");

  await card.getByRole("button", { name: "Approve", exact: true }).click();
  const command = await server.next((c) => c.type === "confirm");
  expect(command).toMatchObject({ confirmation_id: "k1", decision: "approve", feedback: "" });
  await expect(card.getByRole("button", { name: "Approve", exact: true })).toBeDisabled(); // submitting

  server.send("tool_confirmation_resolved", { confirmation_id: "k1", decision: "approve" });
  await expect(card).toHaveCount(0);
  await expect(page.locator(".thinking__step--done", { hasText: "Waiting for your approval" })).toBeVisible();
  assertNoErrors();
});

test("revise needs feedback; reject and approve-all send their decisions", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);
  await runningTurn(page, server);

  server.send("tool_confirmation", FILE_REQUEST);
  const card = page.getByRole("region", { name: "Approval needed: Create a file" });
  await card.getByRole("button", { name: "Revise" }).click();
  const send = card.getByRole("button", { name: "Send feedback" });
  await expect(send).toBeDisabled(); // empty feedback is not allowed
  await card.getByLabel("What should change?").fill("Call it summary.md");
  await send.click();
  expect(await server.next((c) => c.type === "confirm")).toMatchObject({ decision: "revise", feedback: "Call it summary.md" });
  server.send("tool_confirmation_resolved", { confirmation_id: "k1", decision: "revise" });

  server.send("tool_confirmation", { ...FILE_REQUEST, confirmation_id: "k2", args: { ...FILE_REQUEST.args, title: "summary.md" } });
  await page.getByRole("region", { name: "Approval needed: Create a file" }).getByRole("button", { name: "Reject" }).click();
  expect(await server.next((c) => c.type === "confirm")).toMatchObject({ confirmation_id: "k2", decision: "reject" });
  server.send("tool_confirmation_resolved", { confirmation_id: "k2", decision: "reject" });

  server.send("tool_confirmation", {
    confirmation_id: "k3",
    agent: "image",
    tool: "generate_image",
    args: { prompt: "a cup of green tea at sunrise", width: 1024, height: 768 },
    timeout_seconds: 600,
  });
  const image = page.getByRole("region", { name: "Approval needed: Generate an image" });
  await expect(image).toContainText("a cup of green tea at sunrise");
  await expect(image).toContainText("1024×768");
  await image.getByRole("button", { name: "Approve all" }).click();
  expect(await server.next((c) => c.type === "confirm")).toMatchObject({ confirmation_id: "k3", decision: "approve_all" });
});

test("an expired request locks its buttons", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);
  await runningTurn(page, server);
  server.send("tool_confirmation", { ...FILE_REQUEST, timeout_seconds: 1 });
  const card = page.getByRole("region", { name: "Approval needed: Create a file" });
  await expect(card).toContainText("Expired");
  await expect(card.getByRole("button", { name: "Approve", exact: true })).toBeDisabled();
});

test("a pending request is replayed after reconnecting", async ({ page }) => {
  await fakeChatServer(page, {
    onConnect: (ws) =>
      ws.send(JSON.stringify({
        type: "turn_state",
        data: { current: { status: "running", agent: "document", draft: "", pending_confirmations: [FILE_REQUEST] }, queued: [] },
      })),
  });
  await register(page);
  await newChat(page);
  await expect(page.getByRole("region", { name: "Approval needed: Create a file" })).toContainText("green-tea.md");
  await expect(page.locator(".thinking")).toContainText("Waiting for your approval");
});

test("a stale-confirmation error removes only that card, never a queued message", async ({ page }) => {
  const server = await fakeChatServer(page);
  await register(page);
  await newChat(page);
  await runningTurn(page, server);

  await input(page).fill("Queued follow-up");
  await page.getByRole("button", { name: "Queue", exact: true }).click();
  await server.next((c) => c.content === "Queued follow-up"); // not yet confirmed by the server

  server.send("tool_confirmation", FILE_REQUEST);
  const card = page.getByRole("region", { name: "Approval needed: Create a file" });
  await card.getByRole("button", { name: "Approve", exact: true }).click();
  await server.next((c) => c.type === "confirm");
  server.raw({ type: "error", detail: "That confirmation is no longer pending.", command: "confirm", confirmation_id: "k1" });

  await expect(card).toHaveCount(0);
  await expect(page.locator(".composer-queue__item")).toContainText("Queued follow-up"); // untouched
});
