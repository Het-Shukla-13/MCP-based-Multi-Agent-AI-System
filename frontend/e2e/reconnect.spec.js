import { expect, test } from "@playwright/test";
import { newChat, register } from "./helpers";

test("a dropped WebSocket reconnects automatically", async ({ page }) => {
  // Record sockets the app opens so the test can drop one like a network failure.
  // (Chromium's offline emulation does NOT close already-open WebSockets.)
  await page.addInitScript(() => {
    const Native = window.WebSocket;
    window.__sockets = [];
    window.WebSocket = class extends Native {
      constructor(...args) {
        super(...args);
        window.__sockets.push(this);
      }
    };
  });
  await register(page);
  await newChat(page);

  const count = await page.evaluate(() => {
    window.__sockets.at(-1).close();
    return window.__sockets.length;
  });
  await expect(page.locator(".status-pill--reconnecting")).toBeVisible();
  await expect
    .poll(() => page.evaluate((n) => window.__sockets.length > n && window.__sockets.at(-1).readyState === 1, count))
    .toBe(true);
  await expect(page.locator(".status-pill--connected")).toBeVisible();
});
