import { expect, test } from "@playwright/test";
import { newChat, register } from "./helpers";

const inViewport = (locator) =>
  locator.evaluate((el) => {
    const r = el.getBoundingClientRect();
    return r.top >= 0 && r.left >= 0 && r.bottom <= innerHeight + 1 && r.right <= innerWidth + 1;
  });

test("phone layout: drawer navigation, composer always reachable, no overflow", async ({ page }) => {
  await register(page);
  const toggle = page.getByRole("button", { name: "Open conversations" });
  await expect(toggle).toBeVisible();
  expect(await inViewport(page.locator(".sidebar"))).toBe(false);

  await newChat(page); // opens the drawer, creates the chat, drawer closes
  await expect(page.locator(".sidebar--open")).toHaveCount(0);
  expect(await inViewport(page.getByLabel("Chat message input"))).toBe(true);
  expect(await inViewport(page.getByRole("button", { name: "Send" }))).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBe(0);

  await toggle.click();
  await expect(page.locator(".sidebar--open")).toBeVisible();
  await page.locator(".sidebar-backdrop").click({ position: { x: 370, y: 400 } });
  await expect(page.locator(".sidebar--open")).toHaveCount(0);

  await page.getByRole("button", { name: "🧠 Memory" }).click();
  expect(await inViewport(page.getByRole("dialog", { name: "Memory" }))).toBe(true);
});
