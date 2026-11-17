# 42 — Restyle: layout that scrolls right, icons, document answers, toasts, focus

Branch: `feature/fe-restyle` (Phase I)

The visual direction may still be redesigned later, so this branch is **structural**: everything is built from the tokens (note 41). A redesign changes token values, not components.

## Layout: the shell never scrolls; panels do

- **Before:** `.app-shell` and `.workspace` used `min-height: 100vh`, so the **page** grew with the chat and scrolled. The sidebar scrolled away with it, which is why it looked empty in the screenshots.
- **After:** `.app-shell { height: 100dvh; overflow: hidden }`. The sidebar has `overflow-y: auto`, and the message list is the only thing that scrolls in the chat.
- `dvh` (dynamic viewport height) follows mobile browser toolbars, which `vh` does not.

## Reading column and document-style answers

- The message list, the agent bar and the composer share one centred column: `width: min(var(--reading-width), 100%)`, which is 760px. Lines stay readable on wide screens.
- **Assistant answers** have no card: they read like a page. They use `--text-md`, relaxed leading, and proper heading, list and quote spacing.
- **User messages** are compact tinted bubbles on the right, at most 85% wide (88% on phones).
- **A bug this exposed:** `align-self: flex-end` on user messages had never worked. Each message sits in a plain `<div>` wrapper (for the agent-switch line), which is not a flex container. The wrapper is now `.message-row { display: flex; flex-direction: column }`.

## Icons (`lucide-react` 1.67.0)

- The emoji (🤖 💻 📊 🧭 ✎ ⤓ 🗑 ✕ ☰ 🧠) are replaced by a consistent icon set.
- **Why 1.67.0 and not the newest:** the latest release (1.74.0) came out the same day. The rule is to take a version that has been public for at least two weeks.
- **Accessibility:** icon-only buttons keep their old text as `aria-label` (Rename, Export, Delete, Close), so screen readers and the e2e tests (`getByRole("button", { name: "Rename" })`) see the same names. Decorative icons are `aria-hidden`.
- **Pitfall:** `agentIcon()` now returns a React element. Two places had built a **string** with it, which would render "[object Object]". The role label became JSX, and `<option>` uses the label alone, because an `<option>` cannot contain SVG.

## Toasts instead of the status banner

- **Why change it:** the banner pushed the chat down every time something happened, and kept stale text on screen.
- **`useToasts()`:** `notify(message, tone)` with tones info, success, warning and error.
  - Each tone has its own duration; errors stay 8 s.
  - At most 3 are visible, and an identical message is not stacked twice.
  - An empty message is a no-op, because callers used `""` to clear the old banner.
- **Call sites:** `ChatPage` keeps the name `setStatusMessage`, now backed by `notify`. Error call sites pass `"error"` explicitly, rather than having the tone guessed from the text.
- **Accessibility:** errors go in a `role="alert"` region and are announced immediately; everything else goes in `aria-live="polite"`.
- **Placement:** top-right under the header on desktop. The first placement, bottom-right, covered the Send button; the screenshots caught it. On phones they sit at the top, away from the keyboard.
- **Noise removed:**
  - "Conversations loaded." and "Message delivered." just described what was already visible.
  - "No conversations yet" is a **state**, not an event, so it belongs in the empty sidebar, not in a toast (it was going stale after an import).

## One focus style, reduced motion

- `:where(button, a, input, textarea, select, summary, [tabindex]):focus-visible { box-shadow: var(--focus-ring) }`.
  - `:focus-visible` shows the ring for keyboard users, not on mouse clicks.
  - `:where()` has zero specificity, so components can still override it.
- `prefers-reduced-motion: reduce` sets transitions and animations to near-zero across the app.

## Tests

- **e2e updated to the new contract:**
  - `.status-banner` → `.toast`. Because toasts stack, the assertion is "a toast with this text is visible": `locator(".toast", { hasText })`.
  - The "🧠 Memory" button → "Memory".
- **Fast suite:** 12/13 pass. The memory test still fails only because adding a memory needs today's exhausted embedding quota, which the server log confirms with 26 `EmbeddingQuotaExhausted` errors.
- **Visual spec:** both themes on desktop and phone, including the no-overflow assertion.
- Lint and build are clean.
