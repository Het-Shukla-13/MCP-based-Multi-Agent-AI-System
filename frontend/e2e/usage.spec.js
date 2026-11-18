import { expect, test } from "@playwright/test";
import { register, trackPageErrors } from "./helpers";
import { mockUsage } from "./usageFixture";

const open = async (page) => {
  await page.getByRole("button", { name: "Usage" }).click();
  return page.getByRole("dialog", { name: "Usage" });
};

test("tiles, chart with keyboard tooltip, table view, statuses", async ({ page }) => {
  const assertNoErrors = trackPageErrors(page);
  await mockUsage(page);
  await register(page);
  const usage = await open(page);

  await expect(usage.locator(".stat-tile", { hasText: "Replies" })).toContainText("55");
  await expect(usage.locator(".stat-tile", { hasText: "Typical reply time" })).toContainText("4.8 s");
  await expect(usage.locator(".stat-tile", { hasText: "Errors" })).toContainText("Healthy"); // icon + label, not colour alone

  // Every bar is focusable; the tooltip leads with the value.
  const bars = usage.locator(".chart-bar");
  await expect(bars).toHaveCount(7);
  await bars.nth(5).focus();
  await expect(usage.locator(".chart-tooltip strong")).toHaveText("19 replies");
  await expect(usage.locator(".chart-tooltip")).toContainText("1 error");

  // The same numbers without the chart.
  await usage.getByText("Show as table").click();
  await expect(usage.locator(".chart-table tbody tr")).toHaveCount(7);

  await expect(usage.getByRole("list", { name: "Tokens by purpose" }).locator("li").first()).toContainText("Document Agent");
  await expect(usage.locator(".usage-table").first()).toContainText("1 failed");
  assertNoErrors();
});

test("the range filter scopes everything and refetches", async ({ page }) => {
  const requested = await mockUsage(page);
  await register(page);
  const usage = await open(page);
  await expect(usage.locator(".chart-bar")).toHaveCount(7);

  await usage.getByRole("radio", { name: "Last 30 days" }).click();
  await expect(usage.getByRole("radio", { name: "Last 30 days" })).toHaveAttribute("aria-checked", "true");
  await expect(usage.locator(".chart-bar")).toHaveCount(30);
  await expect(usage.locator(".stat-tile", { hasText: "Replies" })).toContainText("in the last 30 days");
  expect(requested).toEqual([7, 30]);
});

test("Esc closes and returns focus to the Usage button", async ({ page }) => {
  await mockUsage(page);
  await register(page);
  const usage = await open(page);
  await expect(usage.getByRole("button", { name: "Close" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(usage).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Usage" })).toBeFocused();
});

test("real backend: a new user sees only their own (empty) usage", async ({ page }) => {
  await register(page); // no mocks: the real /metrics endpoints
  const usage = await open(page);
  await expect(usage.locator(".stat-tile", { hasText: "Replies" })).toContainText("0");
  await expect(usage.getByText("No replies yet")).toBeVisible();
  await expect(usage.locator(".chart-mark")).toHaveCount(0); // no bars for empty days
  await expect(usage.locator(".chart-bar")).toHaveCount(7); // but every day is still on the axis
});
