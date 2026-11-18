import fs from "node:fs";
import { expect, test } from "@playwright/test";
import { newChat, register, trackPageErrors } from "./helpers";

// Search (real backend: Postgres full-text), empty states, drafts, copy, skeletons.
// No LLM: conversations are seeded through the import API.

async function importChat(page, testInfo, title, messages) {
  const file = testInfo.outputPath(`${title.replace(/\W+/g, "-")}.json`);
  fs.writeFileSync(file, JSON.stringify({ format: "mcp-agent-conversation", version: 1, title, messages }));
  await page.locator(".sidebar input[type=file]").setInputFiles(file);
  // Wait for THIS import to finish (it selects the new chat). Waiting for "an Imported
  // toast" returned early when an earlier import's toast was still on screen.
  await expect(page.locator(".workspace-header h2")).toHaveText(title);
}

const LONG_CHAT = [
  { role: "user", content: "Help me plan a trip" },
  ...Array.from({ length: 12 }, (_, i) => ({ role: i % 2 ? "user" : "assistant", content: `Filler message number ${i} about packing lists and weather.` })),
  { role: "assistant", content: "For dinner, try the grilled sardines in Alfama near the cathedral." },
  ...Array.from({ length: 12 }, (_, i) => ({ role: i % 2 ? "user" : "assistant", content: `More filler ${i} about trains and museum hours.` })),
];

test("⌘K finds a conversation by what was said and opens it at that message", async ({ page }, testInfo) => {
  const assertNoErrors = trackPageErrors(page);
  await register(page);
  await importChat(page, testInfo, "Lisbon trip", LONG_CHAT);
  await importChat(page, testInfo, "Python help", [{ role: "user", content: "My tokenizer crashes on unicode" }]);

  await page.getByLabel("Chat message input").click();
  await page.keyboard.press("ControlOrMeta+k");
  const dialog = page.getByRole("dialog", { name: "Search conversations" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("status")).toHaveText("Recent conversations");
  await expect(dialog.getByRole("option")).toHaveCount(2);

  await dialog.getByRole("combobox").fill("sardines");
  const hit = dialog.getByRole("option").first();
  await expect(hit).toContainText("Lisbon trip");
  await expect(hit.locator("mark")).toHaveText("sardines"); // highlighted, rendered as an element (no innerHTML)
  await page.keyboard.press("Enter");

  await expect(dialog).toHaveCount(0);
  await expect(page.locator(".workspace-header h2")).toHaveText("Lisbon trip");
  const target = page.locator(".message", { hasText: "grilled sardines in Alfama" });
  await expect(target).toBeInViewport(); // opened at the match, not at the bottom
  await expect(page.getByRole("button", { name: "Latest" })).toBeVisible();
  assertNoErrors();
});

test("search: keyboard navigation, no results, Esc returns focus", async ({ page }, testInfo) => {
  await register(page);
  await importChat(page, testInfo, "Alpha notes", [{ role: "user", content: "alpha bravo charlie" }]);
  await importChat(page, testInfo, "Beta notes", [{ role: "user", content: "alpha delta echo" }]);

  await page.getByRole("button", { name: /Search chats/ }).click();
  const box = page.getByRole("combobox", { name: "Search conversations" });
  await box.fill("alpha");
  const options = page.getByRole("dialog").getByRole("option"); // (the composer's <select>s have options too)
  await expect(options).toHaveCount(2);
  await expect(options.first()).toHaveAttribute("aria-selected", "true");
  await page.keyboard.press("ArrowDown");
  await expect(options.nth(1)).toHaveAttribute("aria-selected", "true");
  await expect(box).toHaveAttribute("aria-activedescendant", "search-option-1");

  await box.fill("zzzz-nothing-matches");
  await expect(page.getByRole("dialog").getByRole("status")).toHaveText("No matches");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Search chats/ })).toBeFocused(); // focus returned
});

test("empty chat shows starter ideas; a chip fills the composer; drafts survive switching chats", async ({ page }) => {
  await register(page);
  await newChat(page);
  const chip = page.locator(".suggestion-chip", { hasText: "Lisbon" });
  await expect(page.locator(".suggestion-chip")).toHaveCount(6);
  await chip.click();
  const input = page.getByLabel("Chat message input");
  await expect(input).toHaveValue("Plan a relaxed 2-day trip to Lisbon in May");
  await expect(input).toBeFocused();

  await input.fill("half-written thought for chat one");
  await newChat(page); // switch to a second chat
  await expect(input).toHaveValue("");
  await page.locator(".conversation-item").nth(1).locator(".conversation-item__main").click(); // back to chat one
  await expect(input).toHaveValue("half-written thought for chat one");
});

test("Copy answer turns into ✓ Copied and puts the text on the clipboard", async ({ page, context }, testInfo) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await register(page);
  await importChat(page, testInfo, "Copy test", [
    { role: "user", content: "hi" },
    { role: "assistant", content: "The answer to copy.\n\n```python\nprint('hi')\n```" },
  ]);
  const answer = page.locator(".message--assistant").last();
  await answer.getByRole("button", { name: "Copy answer" }).click();
  await expect(answer.locator(".message-meta .copy-button")).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("The answer to copy.");

  await answer.getByRole("button", { name: "Copy code" }).click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("print('hi')");
  await expect(answer.locator(".message-meta .copy-button")).toHaveText("Copy", { timeout: 3000 }); // resets
});

test("a skeleton shows while messages load", async ({ page }, testInfo) => {
  await register(page);
  await importChat(page, testInfo, "Slow chat", [{ role: "user", content: "hello" }]);
  await importChat(page, testInfo, "Other chat", [{ role: "user", content: "other" }]);
  let release;
  const gate = new Promise((resolve) => (release = resolve));
  await page.route(/\/messages\/\?conversation_id=/, async (route) => {
    await gate;
    await route.continue();
  });
  await page.locator(".conversation-item", { hasText: "Slow chat" }).locator(".conversation-item__main").click();
  await expect(page.getByRole("status", { name: "Loading messages" })).toBeVisible();
  release();
  await expect(page.locator(".message--user")).toContainText("hello");
});
