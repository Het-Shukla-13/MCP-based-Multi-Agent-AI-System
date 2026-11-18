# 47 — The flaky tests were a real outage: background jobs starving the DB pool

Branch: `fix/db-pool-starvation` (backend).

## Symptom

- The full e2e suite failed **differently each run**, always by timeout (15 s), and failures **clustered at the end** of a run.
- Back-to-back runs failed sooner; after a pause, a run passed.
- One failure screenshot showed the sign-up button stuck on **"Please wait…"**: `POST /auth/register` never returned.

## Investigation: measure, don't guess

| Hypothesis | Test | Result |
|---|---|---|
| Argon2 hashing blocks the event loop | timed it: ~30 ms per hash/verify | too small for 15 s stalls; not the cause |
| The backend is stalling | probe `/health` every 100 ms during the suite | worst **80 ms**; the backend never stalled |
| An auth rate limiter | searched the code and the 429s in the logs | none exist |
| **Something holds DB connections** | `pg_stat_activity` | **12 connections "idle in transaction" for 2 minutes**, last query `SELECT … FROM memory` |

**The key insight:** `/health` doesn't touch the database. A fast `/health` combined with hanging DB-backed endpoints points straight at the connection pool.

## Root cause

- **The pipeline:** importing a conversation (and every chat turn) schedules the background **memory maintenance pipeline**. It opens **one session**, runs a query (which starts a transaction), then makes **many slow LLM calls** while holding that connection.
- **The lock:** it was locked **per user** only, so N active users meant N pipelines in parallel and N connections held for minutes.
- **The pool:** SQLAlchemy's default pool is 5 + 10 overflow = 15. Once background jobs held 12 or more, every request needing a connection **queued**, for up to 30 s by default, and then failed.
- **Why the tests found it:** e2e tests are many new users importing chats at once. A burst of real users would cause the same outage in production.

## Fix

1. **A global cap** on background maintenance across all users: `MAINTENANCE_MAX_CONCURRENT_RUNS = 2`. It's an `asyncio.Semaphore` acquired *before* the session opens, so background work can never hold more than 2 connections.
2. **An explicit pool:** `pool_size=10`, `max_overflow=10`, **`pool_timeout=10`** (a clear error instead of a 30 s silent hang), and `pool_pre_ping=True` (dead connections are replaced, e.g. after Postgres restarts).

## Proof

- **Unit test** (`tests/test_maintenance_concurrency.py`): 6 users' pipelines run at once and the peak number of open sessions is **2**. With the cap removed the test **fails with peak 6**. Checking that a test catches the bug it was written for is part of writing it.
- **Live:**
  - After the fix, `pg_stat_activity` shows at most **2** "idle in transaction" connections, the cap.
  - The full suite passed **39/39** on two back-to-back runs and two cold-start runs; the third of the first three post-fix runs had one unexplained failure (details lost).

## Still to do (deeper fix)

The pipeline still holds its connection **inside an open transaction** while waiting for LLM calls. "Idle in transaction" also pins a Postgres snapshot, which delays vacuum.

The proper fix is structural:

- end the transaction (commit or rollback) before each external call;
- or split the work into **read → think (no DB) → write** phases, each with a short-lived session.

The cap bounds the damage now; the restructure removes it.

## Lessons

- **A flaky test is a symptom.** "It passes on rerun" was hiding a production outage.
- Compare a DB-free endpoint with DB endpoints to localise a stall.
- Never hold a DB connection, let alone an open transaction, across slow network calls.
- Every *kind* of background work needs a **global** concurrency limit, not just a per-user one.
