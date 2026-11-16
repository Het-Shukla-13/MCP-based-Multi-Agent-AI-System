import { expect, test } from "@playwright/test";
import { PASSWORD, register, trackPageErrors, uniqueEmail } from "./helpers";

test("register, sign out, wrong password, sign back in", async ({ page }) => {
  const assertNoErrors = trackPageErrors(page);
  await page.goto("/");
  await page.getByText("New here? Create an account").click();
  await page.getByLabel("Password").fill("short");
  expect(await page.getByLabel("Password").evaluate((el) => el.validity.tooShort)).toBe(true);

  const email = await register(page, uniqueEmail("auth"));
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  expect(await page.evaluate(() => localStorage.getItem("access_token"))).toBeNull();

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill("wrong-password");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toHaveText("Incorrect email or password");

  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText(email)).toBeAttached();
  assertNoErrors();
});

test("a forged stored session falls back to the sign-in screen", async ({ page }) => {
  await register(page);
  await page.evaluate(() => {
    localStorage.setItem("access_token", "forged.token.value");
    localStorage.setItem("refresh_token", "x".repeat(40));
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
});
