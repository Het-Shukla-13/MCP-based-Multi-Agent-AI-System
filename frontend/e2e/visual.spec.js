import fs from "node:fs";
import { expect, test } from "@playwright/test";
import { register } from "./helpers";

// Screenshots for design review (no pixel assertions: they're compared by eye
// between branches). No LLM: the chat is seeded through conversation import.
// Run: npx playwright test --grep @visual   -> test-results/visual/<name>.png
const OUT = "test-results/visual";
const CHAT = {
  format: "mcp-agent-conversation",
  version: 1,
  title: "Lisbon trip plan",
  messages: [
    { role: "user", content: "Plan a relaxed 2-day trip to Lisbon in May. I like food and views." },
    {
      role: "assistant",
      content:
        "Here's a relaxed plan with good food and the best viewpoints.\n\n" +
        "## Day 1 — Alfama & Baixa\n- Morning: tram 28 to **Miradouro de Santa Luzia**\n- Lunch: grilled sardines in Alfama\n- Evening: sunset at *Miradouro da Graça*\n\n" +
        "## Day 2 — Belém\n| Time | Place | Tip |\n|---|---|---|\n| 10:00 | Jerónimos Monastery | Book online |\n| 12:30 | Pastéis de Belém | Eat them warm |\n| 16:00 | LX Factory | Great for gifts |\n\n" +
        "> May is lovely: around 22 °C and fewer crowds than summer.",
    },
    { role: "user", content: "Can you give me a tiny Python script that converts EUR to INR?" },
    {
      role: "assistant",
      content: "Sure — pass the rate in so the script stays correct when it changes:\n\n```python\ndef eur_to_inr(amount: float, rate: float) -> float:\n    return round(amount * rate, 2)\n\nprint(eur_to_inr(120, 90.5))  # 10860.0\n```",
    },
  ],
};

async function shoot(page, name) {
  await page.waitForTimeout(250); // let transitions settle
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage: false });
}

for (const theme of ["light", "dark"]) {
  test(`@visual screens (${theme})`, async ({ page }, testInfo) => {
    const device = testInfo.project.name;
    await page.addInitScript((t) => window.localStorage.setItem("theme", t), theme);
    await page.goto("/");
    await shoot(page, `${device}-${theme}-login`);

    await register(page);
    const file = testInfo.outputPath("chat.json");
    fs.writeFileSync(file, JSON.stringify(CHAT));
    const drawer = page.getByRole("button", { name: "Open conversations" });
    if (await drawer.isVisible()) await drawer.click();
    await page.locator(".sidebar input[type=file]").setInputFiles(file);
    await expect(page.locator(".message--assistant .message-body").first()).toContainText("relaxed plan");
    if (device === "mobile") await page.mouse.click(370, 400); // tap outside: close the drawer
    // Rich content (tables, long code lines) must scroll inside its block, never widen the page.
    const overflow = await page.evaluate(() => {
      const extra = document.documentElement.scrollWidth - innerWidth;
      const widest = [...document.querySelectorAll("body *")]
        .filter((el) => el.getBoundingClientRect().right > innerWidth + 1 && !el.closest("pre, .md-table-wrap"))
        .map((el) => `${el.tagName.toLowerCase()}.${[...el.classList].join(".")}`)
        .slice(0, 5);
      return { extra, widest };
    });
    // (content inside a scrolling <pre> / table wrapper may be wider: it scrolls there)
    expect(overflow, JSON.stringify(overflow)).toEqual({ extra: 0, widest: [] });
    await shoot(page, `${device}-${theme}-chat`);

    const memory = page.getByRole("button", { name: /memory/i }).first();
    if (device === "desktop" && (await memory.isVisible())) {
      await memory.click();
      await shoot(page, `${device}-${theme}-memory`);
    }
  });
}
