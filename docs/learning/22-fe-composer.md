# 22 · Composer: mentions, pins, drag-and-drop, output format (`feature/fe-composer`)

## @mentions
- The menu opens only for `@` at the **start or after whitespace** (`/(^|\s)@([a-z_]*)$/`), the same rule as the backend parser. `het@code.dev` no longer opens it.
- Choosing an agent **inserts `@code `** into the message (cursor placed after it). The old version deleted the typed text and set hidden state. Now the message text is the single source of truth, and the backend routes on it (branch 10).
- Keyboard: ↑/↓, Enter/Tab to pick, Esc to close. Enter sends, Shift+Enter adds a new line.

## Pinned agent per conversation
An **Agent** dropdown ("🧭 Auto" or a specific agent) is stored per conversation id. A pin in one chat doesn't affect others (the old global `localStorage` value did).

## Drag-and-drop upload
- Drop files anywhere on the chat.
- **`dragover` must call `preventDefault()`**, otherwise the browser opens the dropped file instead of giving it to the page.
- `dragenter`/`dragleave` fire for **every child element** you cross, so a boolean flickers. A **counter** tracks depth and the overlay hides only at 0.

## Client-side checks (`lib/uploads.js`)
Allowed extensions mirror the backend's `file_type_config.py`, plus the 7 MB limit and empty-file checks. Rejected files are listed with reasons ("setup.exe (unsupported type), huge.txt (larger than 7 MB)") and valid ones still upload. This is only **instant feedback**: the server stays the gatekeeper (it also checks magic bytes), because client checks can be bypassed. `accept=` on the file picker filters the dialog too.

## Output format
"Reply as PDF / Markdown / text / CSV / JSON" sends `format` with the message. The backend asks the agent to deliver a file via `create_file` (branch 12). The picker resets after sending, so a PDF choice isn't silently reused.

## Also
- Last lint error fixed (a callback used `handleSubmit` before it was declared): **lint is now clean (0 errors, 0 warnings).**
- Notes index row for note 21 added.

## Browser-verified (Playwright)
- e-mail → no menu; `@co` → `@code`, Enter inserts `"@code "`, reply labelled Code Agent.
- Pin "data" in chat 1 → new chat shows Auto → chat 1 still data.
- Drop sales.csv + setup.exe + 8 MB file → overlay shown, only sales.csv uploaded, both rejections named.
- "Reply as PDF" → PDF attached to the reply, picker reset. No page errors.

*Testing lesson:* the first run reported "data" in the new chat. That was a **race in the test** (it waited for "connected", which the old chat already was). Wait for a condition that proves the *new* state (the new title), not one that was already true.
