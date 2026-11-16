# 24 · Memory panel and conversation management (`feature/fe-memory-and-conversations`)

## Conversations (sidebar)
- **Rename** inline (Enter saves, Esc cancels, blur saves) via `PATCH /conversations/{id}`.
- **Delete** with confirmation; the next chat is selected and cached messages are dropped.
- **Export:** the JSON is fetched with the token, turned into a `Blob`, and downloaded by "clicking" a temporary `<a download>`. `URL.revokeObjectURL` then frees the in-memory file. (A plain link can't be used: export needs the Authorization header.)
- **Import:** a hidden file input; the JSON is parsed in the browser (invalid JSON gets a clear message) and sent to `POST /conversations/import`, which creates a new chat and rebuilds memories in the background.
- Actions appear on hover, keyboard focus or the active item.

## Memory panel (🧠 Memory → slide-over drawer)
- **Memories tab:**
  - list (optionally including inactive), plus semantic **search** with the distance shown;
  - **add** ("teach the assistant"), inline **edit** (the backend re-embeds), **deactivate/reactivate** (reversible), **delete** (permanent, confirmed).
- **Profile tab:** the derived profile by section; remove an item; rebuild.
- Esc or a click on the backdrop closes it. `role="dialog"` and `role="tab"`/`aria-selected` for accessibility.

## Lint notes
- React's lint can't see that a state update inside an `async` function happens after `await`. Writing `fetchProfile().then(setProfile)` makes the asynchronous update explicit.
- Removing a key from state: copy the object and `delete` from the copy (never mutate the existing state object).

## Browser-verified (Playwright)
Rename → export (file `Renamed_chat.json`, format `mcp-agent-conversation`, 2 messages) → import as a new chat (reply visible) → delete → add memory → search (distance 0.769) → edit → profile shows **only** the new wording (after the backend fix in note 23) → deactivate removes it from the profile → hard delete → Esc closes. No page errors.

**Frontend status:** all lint clean, builds, and every feature has been exercised in a real browser.
