# 41 — Design tokens, light/dark without flash, and a warmer look

Branch: `feature/fe-design-tokens` (Phase I)

## Why

- **Feedback on the old UI:** "very negative vibes". It had a near-black navy background everywhere, cold slate greys, heavy translucent dark panels, and red/amber blocks for status.
- **No system behind it:** there were about **60 different hard-coded colours** (81 hex values plus many one-off `rgba`s, such as 8 opacities of the same slate border), font sizes from 0.72 to 0.9rem, and 12 different radii.
- **No theme support:** there was no light theme and no way to add one.

## Tokens (`src/tokens.css`)

Two levels:

1. **Scales** that don't depend on the theme:
   - type: `--text-xs` to `--text-2xl`; leading; weights;
   - spacing: `--space-1` to `--space-10`, on a 4px base;
   - radius: `--radius-sm` to `--radius-pill`;
   - motion: `--duration`, `--ease`;
   - layout widths.
2. **Semantic colours**, named by role, never by hue:
   - `--bg`, `--surface`, `--surface-raised`, `--surface-subtle`, `--surface-sunken`, `--surface-hover`, `--input-bg`, `--overlay`;
   - `--border`, `--border-strong`;
   - `--text`, `--text-secondary`, `--text-muted`, `--text-on-accent`;
   - `--accent`, `--accent-hover`, `--accent-text`, `--accent-soft`, `--accent-border`;
   - `--user-bubble`;
   - `--success`, `--warning` and `--danger`, each with `*-text` and `*-soft` variants;
   - `--code-bg`, `--code-text`;
   - the shadow scale and `--focus-ring`.

Components use **only** semantic tokens, so a theme is just another set of values for the same names. `--accent` is a single knob for the brand colour.

**The look:**

- **Light (default):** warm off-white `#faf8f5`, white surfaces, soft warm borders instead of heavy shadows, and one calm teal accent.
- **Dark:** warm charcoal `#161615`, not navy.
- **Status colours:** gentle tinted backgrounds rather than saturated blocks.
- **Fonts:** Inter, self-hosted through `@fontsource-variable/inter` (pinned to 5.3.0, so there is no request to a font CDN), and a real monospace stack for code.

## Accessibility is computed, not eyeballed

`scripts/check-contrast.py` parses `tokens.css` and computes the WCAG contrast ratio for every text/background pair in both themes. It exits 1 below AA (4.5:1).

It caught two light-theme failures:

- white text on the accent: 4.25;
- muted text on the subtle surface: 4.28.

Both were fixed by darkening the accent and the muted grey slightly. All pairs now pass AA.

## Light/dark without a flash

- **The problem:** React applies a theme only after the JS bundle runs, so a dark-mode user would see a white flash on every load.
- **The fix:** a 6-line inline `<script>` in `index.html` `<head>` reads `localStorage.theme` (or the OS preference) and sets `<html data-theme>` **before the first paint**.
- `src/lib/theme.js` mirrors that logic. Its preference is `system`, `light` or `dark`, and while it is `system` it follows OS changes live.
- Storage access sits inside `try`, because private mode can throw.
- `ThemeToggle` cycles Auto → Light → Dark. It lives in the sidebar footer next to "Sign out", and in a corner of the sign-in page.
- `<meta name="theme-color">` per scheme tints the mobile browser chrome.

## The migration: by role, not by value

The same slate grey was text in one rule and a border in another, so a plain find-and-replace would be wrong. A script parsed every declaration and mapped (**property role**, colour) to a token:

- `color` → text tokens;
- `background` → surface or soft tokens;
- `border` / `outline` → border tokens;
- font sizes and radii → their scales.

It reported anything unmapped. The leftovers (4 shadows, a border hidden behind a comment that contained `:`, the navy body gradient) were mapped by hand. Afterwards there are **0 raw colours** in `styles.css`.

## Visual review: `e2e/visual.spec.js` (`npm run test:visual`)

- **What it does:** seeds a realistic chat (lists, a table, a quote, code) through the import API, with **no LLM**, and screenshots the login page, the chat and the memory panel in both themes on desktop and phone.
- **What it is for:** comparing branches by eye before and after; it makes no pixel assertions. It is excluded from `test:e2e:fast`.

It found and fixed three bugs:

1. **Dark text on teal buttons.** The old white text had been mapped to `--text`. Text on accent fills must use `--text-on-accent`.
2. **Code in Courier.** A `<code>` inside `<pre>` falls back to the UA default `monospace` and does not inherit the font, so it needs `.md-code pre code { font-family: inherit }`.
3. **Phone cards clipped on the right.**
   - **Cause:** `.workspace` was a grid with no column template. The implicit `auto` track can't shrink below its content's `min-content`, so one long code line widened the whole column.
   - **Fix:** `grid-template-columns: minmax(0, 1fr); min-width: 0`.
   - **New guard:** the visual spec now asserts that rich content never widens the page (anything inside a scrolling `pre` or table wrapper is allowed).

## Verified

- Contrast is AA for all pairs.
- Lint and build are clean.
- The fast e2e suite: 12/13 pass. The failing memory test can't add a memory today because the embedding quota is exhausted, which the backend log confirms; it is not a UI change.
- The visual spec passes, including the no-overflow assertion.

## Follow-ups

- **Backend:** `EmbeddingQuotaExhausted` surfaces as HTTP 500. It should be a 503 with a clear message, so the UI can show "memory temporarily unavailable".
- **`fe-restyle`:** icons instead of emoji, document-style answers in a reading column, and independent scrolling for the sidebar and the chat. On desktop the whole page scrolls today, which takes the sidebar out of view.
