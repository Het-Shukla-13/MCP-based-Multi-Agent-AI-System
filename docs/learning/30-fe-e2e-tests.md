# 30 · Committed end-to-end tests (`feature/fe-e2e-tests`)

## Run them
Docker up and backend on :8000, then from `frontend/`:
```bash
npx playwright install chromium   # once
npm run test:e2e:fast             # 13 tests, no LLM calls (~15 s)
npm run test:e2e                  # all 15, including @llm (~0.5-1.5 min)
npm run test:e2e:report           # HTML report with traces/screenshots of failures
```
The config starts the Vite dev server itself (or reuses a running one).

## What's covered (`frontend/e2e/`)
| Spec | Checks |
|---|---|
| auth | browser validation, register, sign out clears tokens, wrong-password message, sign back in, forged session → sign-in |
| session | 5 parallel 401s → **one** refresh, all succeed, token rotated; refresh before WebSocket; sign-out revokes server-side |
| composer | e-mail ≠ mention, `@co` → `@code `, per-chat pin, drag-and-drop with rejected-file reasons |
| conversations | import a crafted export → rename → export (same messages) → delete; invalid JSON message |
| memory | add, semantic search, edit, profile shows only the new wording (regression for note 23), deactivate, delete, Esc |
| reconnect | dropped socket → "reconnecting" → new open socket → "connected" |
| mobile (iPhone 13) | drawer, composer reachable, no overflow, backdrop closes, memory drawer fits |
| chat **@llm** | streaming + per-message agent labels survive reload, code block rendered, tables, no HTML execution |

## Writing stable tests (lessons from this project)
- **Every test registers a fresh user**, so tests share nothing and can run in parallel.
- **Wait on conditions, never on fixed sleeps:** web-first assertions (`await expect(locator).toHaveText(...)`) retry until true or the timeout.
- **Assert only what's deterministic.** The LLM router choosing an agent for open text is a judgement call (that test was flaky). `@general` is rule-based, so the test pins it.
- **Budget for real dependencies:** embedding steps can wait on the free-tier rate limiter, so they get a longer timeout.
- **Flaky ≠ test problem:** the memory test failed only under parallel load, and the cause was a real **stale-response race in the UI** (note 29). Running tests in parallel puts load on the system and exposes timing bugs.
- `.gitignore` excludes `test-results/` and `playwright-report/`; ESLint treats `e2e/` as Node code (`process`, `fs`).

**Result:** 15/15, twice in a row, lint clean.
