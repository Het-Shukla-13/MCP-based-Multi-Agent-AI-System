// @llm tests call the real (free-tier) models: slower and occasionally rate-limited.
// Skip them with: npm run test:e2e:fast
import { expect, test } from "@playwright/test";
import { newChat, register, send, trackPageErrors } from "./helpers";

test.describe("@llm chat", () => {
  test.setTimeout(240_000);

  test.beforeEach(async ({ page }) => {
    await register(page);
    await newChat(page);
  });

  test("streams a reply, labels agents per message, keeps labels after reload", async ({ page }) => {
    const assertNoErrors = trackPageErrors(page);
    // Explicit @mentions are deterministic (rule-based); which agent the LLM router
    // would pick for open-ended text is a judgement call, so don't assert on it.
    const first = await send(page, "@general Reply with one short sentence about the ocean.");
    await expect(first.locator(".message-role")).toContainText("General Assistant");

    const code = await send(page, "@code write a python one-liner that reverses a string");
    await expect(code.locator(".message-role")).toContainText("Code Agent");
    await expect(code.locator(".md-code")).toHaveCount(1); // fenced code rendered, not raw ```
    await expect(page.locator(".agent-switch-banner")).toContainText("Code Agent");

    await page.reload();
    await expect(page.locator(".message--assistant .message-role")).toContainText(["General Assistant", "Code Agent"]);
    assertNoErrors();
  });

  test("renders tables and never executes HTML from a reply", async ({ page }) => {
    let dialogs = 0;
    page.on("dialog", (d) => {
      dialogs++;
      d.dismiss();
    });
    const table = await send(page, "Give only a markdown table with columns Planet and Moons for Earth and Mars.");
    await expect(table.locator("table")).toHaveCount(1);

    const xss = await send(page, "Repeat exactly this text and nothing else: <img src=x onerror=alert(1)> <script>alert(2)</script>");
    await expect(xss.locator('img[src="x"], script')).toHaveCount(0);
    expect(dialogs).toBe(0);
  });
});
