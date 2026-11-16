import { expect } from "@playwright/test";

export const PASSWORD = "good-password-1";
export const API = process.env.E2E_API_URL || "http://127.0.0.1:8000";

/** Each test gets a brand-new account, so tests never see each other's data. */
export function uniqueEmail(prefix = "e2e") {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}@example.com`;
}

export async function register(page, email = uniqueEmail()) {
  await page.goto("/");
  await page.getByText("New here? Create an account").click();
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(email)).toBeAttached();
  return email;
}

export async function newChat(page) {
  const before = await page.locator(".conversation-item").count();
  const toggle = page.getByRole("button", { name: "Open conversations" });
  if (await toggle.isVisible()) await toggle.click(); // mobile drawer
  await page.getByRole("button", { name: "New Chat", exact: true }).click();
  await expect(page.locator(".conversation-item")).toHaveCount(before + 1);
  await expect(page.locator(".status-pill--connected")).toBeVisible();
}

/** Send a message and wait until the reply is complete (not streaming, not pending). */
export async function send(page, text, { timeout = 120_000 } = {}) {
  const replies = page.locator(".message--assistant");
  const before = await replies.count();
  await page.getByLabel("Chat message input").fill(text);
  await page.getByRole("button", { name: "Send" }).click();
  await expect(replies).toHaveCount(before + 1, { timeout });
  await expect(page.locator(".stream-cursor, .message--pending")).toHaveCount(0, { timeout });
  return replies.last();
}

/** Fail the test on uncaught page errors. */
export function trackPageErrors(page) {
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  return () => expect(errors, "uncaught page errors").toEqual([]);
}
