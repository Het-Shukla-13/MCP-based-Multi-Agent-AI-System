# 45 — Tool confirmations in the UI (+ a protocol fix for error attribution)

Branches: `fix/ws-error-attribution` (backend, merged into develop-be first) and `feature/fe-confirmations` (Phase J).

## The protocol fix came first (backend first)

- **The latent bug, while planning:** "Nothing is running." (Stop) and "That confirmation is no longer pending." (Confirm) had the **same shape** as a rejected *send* (`{type: "error", detail}`). The client's rejected-command logic would have undone the newest unconfirmed **message** for a failed **confirm**.
- **Why a client-side guess wasn't enough:** remembering "the last command I sent" races when two commands are in flight.
- **The fix, in the protocol:** every rejection echoes `command` plus the ids from the command (`client_id`, `confirmation_id`, `turn_id`). It goes through one `reject()` helper in `ws.py`.
- **Turn failures** from the runner have no `command`, so they are told apart by that.
- **Test:** `tests/test_ws_errors.py` drives the real endpoint with FastAPI's `TestClient` WebSocket, with auth, ownership and the runner stubbed.

**Client rule:** `error.command` present → a rejected command, so undo exactly that one:

- `send` → remove that `client_id` (its chip or its running bubble);
- `confirm` → remove that stale card;
- `stop` / `dequeue` → toast only.

Otherwise, `turn_id` present → that turn failed.

## The UI

- **Opting in:** every send now has `confirm_tools: true`. The backend only asks clients that declared they can answer, which is why older UIs never hung (note 37).
- **Events and state:**
  - `tool_confirmation` adds a card with an expiry (`now + timeout_seconds`).
  - `tool_confirmation_resolved` removes it.
  - `turn_state.current.pending_confirmations` restores cards after a reconnect.
  - Cards are cleared when a turn ends.
- **Checklist:**
  - a new step, "Waiting for your approval" (the `awaiting_approval` event), is ticked on `approval_resolved`;
  - because the tool's "Using create file" step has already started, the approval appears right after it;
  - screen readers hear it through the checklist's single live region.
- **`ConfirmationCard`:**
  - "*Document Agent* wants to create a file", the expiry ("expires in 9:42"), and a per-tool summary:
    - create_file: title, `.format`, and a `<details>` content preview;
    - template: template, title, and the fields as a `<dl>`;
    - generate_image: the prompt and size;
    - unknown tools: a generic list of arguments.
  - **Approve · Approve all · Revise · Reject.** Revise opens a feedback box, and Send stays disabled until there is text (the server also requires feedback).
  - Buttons are disabled while a decision is in flight (`submitting`), and **lock at expiry**, when the server treats it as rejected.
  - It **doesn't steal focus**: you may be typing a follow-up in the composer. It's a labelled region (`aria-label="Approval needed: …"`).

## Tests (`e2e/confirmations.spec.js`, against the fake server)

1. Approve:
   - the card shows title, format, preview and expiry;
   - the "Waiting for your approval" step appears;
   - the command is `{confirmation_id, decision: "approve", feedback: ""}`;
   - the button is disabled while submitting;
   - the card clears and the step is ticked.
2. Revise requires feedback; Reject and Approve all send their decisions; the image summary is shown.
3. Expiry locks the buttons.
4. A replayed pending request after reconnecting.
5. **Regression for the protocol fix:** a stale-confirm error removes only the card. A not-yet-confirmed queued message is untouched.

- The composer tests were updated to the new error shape (`command`, `client_id`).
- The visual spec adds the card in both themes.

## Verified

- Backend: 116 tests pass.
- Frontend fast suite: 26/27. The memory test is blocked only by the embedding quota.
- The visual spec passes; lint and build are clean.
