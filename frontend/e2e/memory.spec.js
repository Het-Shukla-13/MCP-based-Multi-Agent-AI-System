import { expect, test } from "@playwright/test";
import { register } from "./helpers";

// Adding, searching and editing memories call Gemini embeddings (free tier: 100/min).
// When other tests use the quota, the backend's rate limiter WAITS (up to ~60 s)
// instead of failing, so these steps get a budget longer than that wait.
const EMBEDDING_STEP = { timeout: 90_000 };

test("add, search, edit, deactivate and delete a memory; profile follows", async ({ page }) => {
  test.setTimeout(240_000);
  page.on("dialog", (dialog) => dialog.accept());
  await register(page);
  await page.getByRole("button", { name: "🧠 Memory" }).click();
  const panel = page.getByRole("dialog", { name: "Memory" });
  await expect(panel).toBeVisible();

  await page.getByPlaceholder("e.g. I prefer concise").fill("I prefer TypeScript for frontend projects.");
  await page.getByRole("button", { name: "Add memory" }).click();
  await expect(page.locator(".memory-row__content")).toHaveText(["I prefer TypeScript for frontend projects."], EMBEDDING_STEP);

  await page.getByPlaceholder("Search by meaning").fill("which language for web UIs?");
  await page.getByRole("button", { name: "Search" }).click();
  await expect(page.locator(".memory-row__meta").first()).toContainText("distance", EMBEDDING_STEP);
  await page.getByPlaceholder("Search by meaning").fill("");

  await page.locator(".memory-row").first().getByRole("button", { name: "Edit" }).click();
  await page.locator(".memory-edit").fill("I prefer TypeScript with React for frontend projects.");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.locator(".memory-row__content")).toHaveText(["I prefer TypeScript with React for frontend projects."], EMBEDDING_STEP);

  await page.getByRole("tab", { name: "Profile" }).click();
  // Regression (fix/profile-stale-items): only the edited wording, not old + new.
  await expect(page.locator(".profile-section li span")).toHaveText(["I prefer TypeScript with React for frontend projects."]);

  await page.getByRole("tab", { name: "Memories" }).click();
  await page.locator(".memory-row").first().getByRole("button", { name: "Deactivate" }).click();
  await expect(page.locator(".memory-row")).toHaveCount(0);
  await page.getByRole("tab", { name: "Profile" }).click();
  await expect(page.locator(".profile-section li")).toHaveCount(0);

  await page.getByRole("tab", { name: "Memories" }).click();
  await page.getByLabel("show inactive").check();
  await page.locator(".memory-row").first().getByRole("button", { name: "Delete" }).click();
  await expect(page.locator(".memory-row")).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(panel).toHaveCount(0);
});
