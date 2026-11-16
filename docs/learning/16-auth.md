# 16 · Authentication and authorization (`feature/auth`)

## Before
33 of 37 routes trusted a `user_id` sent by the client, or didn't check ownership at all:
- `GET /users/` listed every user, and anyone could read any conversation by id.
- The WebSocket trusted `?user_id=`.
- Passwords were stored **in plaintext**.

## Authentication = who are you?
**Passwords → Argon2id** (`app/core/security.py`, `argon2-cffi`):
- *Slow and memory-hard* (64 MB, 3 passes), so cracking a stolen DB with GPUs is expensive. Fast hashes like SHA-256 are wrong for passwords.
- Each hash embeds a **random salt** and its parameters (`$argon2id$v=19$m=65536,t=3,p=4$...`), so the same password gives different hashes.
- `needs_rehash` upgrades old hashes on login if the parameters are strengthened later.

**Migration of existing plaintext passwords:** rename the column, then hash every value in place inside the migration (idempotent: rows that already start with `$argon2` are skipped). No user resets anything. Verified: a migrated user logs in with the old password.

**Tokens → JWT (HS256)** with `sub`=user id, `exp`=60 min, `type`=access. The server checks the signature + expiry without a DB lookup.
- A JWT is **signed, not encrypted**: anyone can read it, so put only the id inside.
- `algorithms=[...]` is **pinned** when decoding, so `alg: none` tokens are rejected.
- `JWT_SECRET` has **no default**: the app refuses to start without one (a guessable key = anyone can mint tokens).

**Login hygiene:** the same message for "unknown email" and "wrong password", plus a dummy hash check for unknown emails so the response time doesn't reveal which emails are registered.

## Authorization = what may you touch?
`app/api/deps.py`:
- `get_current_user`: identity **only** from the token.
- `owned_conversation / owned_file / owned_message / owned_memory`: query by id **and** user. Missing and not-yours both return **404**; a 403 would confirm the id exists.
- `get_conversations(user_id)` is now **required**. An optional filter that defaults to "everyone" is one forgotten argument away from a leak.

**Where headers can't be sent:**
- **WebSocket:** browsers can't set headers, so `?token=`. The user is derived from it.
- **File download/raw/preview:** `<a href>`, `<img src>` and `<iframe>` can't send headers either, so they also accept `?token=`. The preview page puts the token into its own embedded links and sets `<meta name="referrer" content="no-referrer">`, so the token isn't leaked to other sites via `Referer`. URL tokens can land in logs/history, so they're limited to these read-only routes and expire in 60 min.

## API changes
- New: `POST /auth/register`, `POST /auth/login`, `GET /auth/me`.
- `/users/*` → `/users/me` (GET, PATCH with **current password re-check**, DELETE). Listing or editing other users is gone.
- Conversations, messages, files, chat, memories, profile (`/memories/profile`): all scoped to the token's user; no `user_id` parameters.
- Raw `POST/PUT /messages` removed: messages go through chat, so they always pass through agents + memory.
- `DELETE /files/{id}` implemented: DB row (chunks cascade) + bytes on disk, only inside `uploads/` or `generated/`.

## Verified
- Unit (`tests/test_security.py`): salted hashes, token roundtrip, **tampered payload**, **`alg: none`**, expired token, wrong key → all rejected.
- Live two-user attack: 22/22 checks pass (B gets 404 on everything of A's, A's items invisible in B's lists, WebSocket rejected, same login error for unknown email vs wrong password, migrated login works).

Tests: 34 passed.
