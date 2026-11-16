import { expect, test } from "@playwright/test";
import { API, newChat, register } from "./helpers";

test("parallel 401s share ONE refresh and the requests succeed", async ({ page }) => {
  await register(page);
  let refreshCalls = 0;
  page.on("request", (r) => r.url().endsWith("/auth/refresh") && refreshCalls++);
  const oldRefresh = await page.evaluate(() => localStorage.getItem("refresh_token"));

  await page.evaluate(() => localStorage.setItem("access_token", "corrupted.token.value"));
  const results = await page.evaluate(async () => {
    const { fetchConversations } = await import("/src/lib/api.js");
    return Promise.all(Array.from({ length: 5 }, () => fetchConversations().then(() => "ok", () => "fail")));
  });

  expect(results).toEqual(["ok", "ok", "ok", "ok", "ok"]);
  expect(refreshCalls).toBe(1); // single-flight: two refreshes would trip reuse detection
  await expect.poll(() => page.evaluate(() => localStorage.getItem("refresh_token"))).not.toBe(oldRefresh);
});

test("an expiring token is refreshed before the WebSocket connects", async ({ page }) => {
  await register(page);
  await page.evaluate(() => localStorage.setItem("access_expires_at", String(Date.now() + 5_000)));
  const refresh = page.waitForRequest((r) => r.url().endsWith("/auth/refresh"));
  await newChat(page);
  await refresh;
});

test("sign out revokes the refresh token on the server", async ({ page, request }) => {
  await register(page);
  const refreshToken = await page.evaluate(() => localStorage.getItem("refresh_token"));
  await Promise.all([
    page.waitForResponse((r) => r.url().endsWith("/auth/logout")),
    page.getByRole("button", { name: "Sign out" }).click(),
  ]);
  const response = await request.post(`${API}/auth/refresh`, { data: { refresh_token: refreshToken } });
  expect(response.status()).toBe(401);
});
