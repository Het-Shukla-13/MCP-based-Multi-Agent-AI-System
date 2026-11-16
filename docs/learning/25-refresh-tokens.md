# 25 · Refresh tokens with rotation and reuse detection (`feature/refresh-tokens`)

## Problem
Access tokens last 60 minutes and there was no way to renew them, so a long session ended with a sudden logout. Making access tokens last days would be worse: a JWT can't be revoked before it expires.

## Two tokens, two jobs
| | Access token | Refresh token |
|---|---|---|
| Lifetime | 60 min | 7 days |
| Format | JWT (verified without DB) | Random string (looked up in DB) |
| Sent | On every API call | Only to `/auth/refresh` and `/auth/logout` |
| Revocable | No (expires fast) | Yes (DB row) |

## Storage
Only a **SHA-256 hash** is stored (`refresh_token.token_hash`), so a database leak doesn't hand out working sessions. SHA-256, not Argon2: slow hashing protects *guessable* human passwords. A 384-bit random token can't be guessed, so a fast hash is the right tool.

## Rotation + reuse detection (OAuth 2.0 Security Best Current Practice)
- Every `/auth/refresh` revokes the presented token and returns a **new** one in the same **family** (the chain started by one login).
- If a token that was **already used** is presented again, two parties hold it, i.e. it was stolen. The **whole family is revoked**: the thief *and* the victim are logged out of that session, and the victim signs in again.
- `/auth/logout` revokes the family server-side, so the refresh token is dead even if a copy exists somewhere.

## Verified live
1. register → refresh token (7 days)
2. refresh → 200, rotated, new access token works
3. replay the old token → 401
4. the victim's current token → 401 (session revoked)
5. a new login works
6. logout → 204, then refresh → 401
7. garbage → 401

The DB holds 64-char hashes only. Tests: 36 passed.
