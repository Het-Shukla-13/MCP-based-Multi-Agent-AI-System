import fs from "node:fs";
import { expect, test } from "@playwright/test";
import { register } from "./helpers";

// No LLM needed: the conversation is created by importing a crafted export file.
const EXPORT = {
  format: "mcp-agent-conversation",
  version: 1,
  title: "Imported trip plan",
  messages: [
    { role: "user", content: "Plan a weekend in Udaipur" },
    { role: "assistant", content: "Day 1: City Palace. Day 2: Lake Pichola." },
  ],
};

test("import, rename, export and delete a conversation", async ({ page }, testInfo) => {
  await register(page);
  const file = testInfo.outputPath("import.json");
  fs.writeFileSync(file, JSON.stringify(EXPORT));

  await page.locator(".sidebar input[type=file]").setInputFiles(file);
  await expect(page.locator(".toast", { hasText: "Imported 2 messages" })).toBeVisible();
  await expect(page.locator(".message--assistant .message-body")).toContainText("Lake Pichola");

  const item = page.locator(".conversation-item").first();
  await item.getByRole("button", { name: "Rename" }).click();
  await page.getByLabel("Conversation title").fill("Udaipur weekend");
  await page.getByLabel("Conversation title").press("Enter");
  await expect(page.locator(".workspace-header h2")).toHaveText("Udaipur weekend");

  const [download] = await Promise.all([page.waitForEvent("download"), item.getByRole("button", { name: "Export" }).click()]);
  const exported = JSON.parse(fs.readFileSync(await download.path(), "utf8"));
  expect(download.suggestedFilename()).toBe("Udaipur_weekend.json");
  expect(exported.messages.map((m) => m.content)).toEqual(EXPORT.messages.map((m) => m.content));

  page.once("dialog", (dialog) => dialog.accept());
  await item.getByRole("button", { name: "Delete" }).click();
  await expect(page.locator(".conversation-item")).toHaveCount(0);
});

test("importing a file that is not JSON shows a clear error", async ({ page }, testInfo) => {
  await register(page);
  const file = testInfo.outputPath("broken.json");
  fs.writeFileSync(file, "{not json");
  await page.locator(".sidebar input[type=file]").setInputFiles(file);
  await expect(page.locator(".toast", { hasText: "That file is not valid JSON." })).toBeVisible();
});
