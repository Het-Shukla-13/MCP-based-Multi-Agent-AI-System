import { expect, test } from "@playwright/test";
import { newChat, register } from "./helpers";

test.beforeEach(async ({ page }) => {
  await register(page);
  await newChat(page);
});

test("@ menu ignores e-mail addresses and inserts the chosen agent", async ({ page }) => {
  const input = page.getByLabel("Chat message input");
  await input.pressSequentially("mail me at het@code");
  await expect(page.locator(".mention-dropdown")).toHaveCount(0);

  await input.fill("");
  await input.pressSequentially("@co");
  await expect(page.locator(".mention-option__name")).toHaveText(["@code"]);
  await input.press("Enter");
  await expect(input).toHaveValue("@code ");
});

test("agent pin is per conversation", async ({ page }) => {
  await page.getByRole("combobox").first().selectOption("data");
  await newChat(page);
  await expect(page.getByRole("combobox").first()).toHaveValue("");
  await page.locator(".conversation-item", { hasText: "New Chat 1" }).locator(".conversation-item__main").click();
  await expect(page.getByRole("combobox").first()).toHaveValue("data");
});

test("drag-and-drop uploads valid files and names the rejected ones", async ({ page }) => {
  const dataTransfer = await page.evaluateHandle(() => {
    const dt = new DataTransfer();
    dt.items.add(new File(["region,revenue\nNorth,10\n"], "sales.csv", { type: "text/csv" }));
    dt.items.add(new File(["MZ"], "setup.exe"));
    dt.items.add(new File(["x".repeat(8 * 1024 * 1024)], "huge.txt", { type: "text/plain" }));
    return dt;
  });
  await page.dispatchEvent(".chat-window", "dragenter", { dataTransfer });
  await expect(page.locator(".drop-overlay")).toBeVisible();
  await page.dispatchEvent(".chat-window", "drop", { dataTransfer });

  await expect(page.locator(".composer-file-chip")).toHaveCount(1);
  await expect(page.locator(".composer-file-chip").first()).toContainText("sales.csv");
  await expect(page.locator(".toast", { hasText: "setup.exe (unsupported type)" })).toBeVisible();
  await expect(page.locator(".toast", { hasText: "huge.txt (larger than 7 MB)" })).toBeVisible();
});
