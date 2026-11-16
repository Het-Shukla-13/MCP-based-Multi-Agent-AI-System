# 31 · Frontend README (`docs/fe-readme`)

`frontend/README.md` replaced the default Vite template text with:
- features at a glance, quick start, scripts;
- project structure (what each file is for);
- **how it works:** session/refresh flow, WebSocket protocol, reconnect, state principles (derive don't copy, latest request wins, per-conversation state);
- **security notes:** why there's no raw HTML (token in localStorage), client checks are feedback only, CSP on previews;
- end-to-end tests and **troubleshooting**, including the "CORS error that is really a 500" lesson.

The root README gained frontend setup, browser-test steps, and the session/realtime design decisions.

**Why it matters:** a README is the project's user interface for developers. It records the *why* behind decisions, so the next person (or you, in six months) doesn't undo them by accident (e.g. adding `rehype-raw`).
