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

## The deeper fix (`fix/pipeline-connection-release`)

The cap bounded the damage; the pipeline still held its connection **inside an open transaction** during every LLM call. "Idle in transaction" also pins a Postgres snapshot, which delays vacuum.

- **`app/db/slow_io.py`:** a job opts its session in with `async with AsyncSessionLocal() as db, release_connection_during_slow_io(db):`.
- **The hook:** the two async choke points for slow calls, `get_llm_response_async` and `embed_text_async`, call `before_slow_io()`. That **commits** the read-only transaction, so the connection returns to the pool; the next query takes a fresh one.
- **The safety rules:**
  - Commit, never rollback: a rollback would silently discard **flushed** writes, which don't appear in `db.new`/`db.dirty`.
  - With **unflushed** pending changes it does nothing (logged).
  - `expire_on_commit=False` keeps loaded objects usable.
  - It only acts in the **task that opted in**, because tasks spawned inside the job copy the ContextVar and must not commit someone else's session.
- **Tests (real Postgres):**
  - after a read, `before_slow_io()` drops the pool's checked-out count from 1 to 0, and the session still works;
  - unflushed changes keep the transaction;
  - a spawned task can't release the session;
  - nothing happens without the opt-in.
- **Measured live:** `pg_stat_activity` was sampled every second during the full e2e suite (which triggers many pipelines).

| | longest "idle in transaction" |
|---|---|
| original bug | ~120 s (12 connections) |
| with the concurrency cap only | ~23 s (2 connections) |
| **with connection release** | **0.1 s** |

The suite passed 47/47 during the measurement. **A measurement lesson from the way here:** the first attempt reported "0.0 s" from only 4 samples and no test result. The checkout was on the backend branch, whose copy of the frontend was stale, so the suite never ran. A number from a run you didn't verify isn't evidence.

## Lessons

- **A flaky test is a symptom.** "It passes on rerun" was hiding a production outage.
- Compare a DB-free endpoint with DB endpoints to localise a stall.
- Never hold a DB connection, let alone an open transaction, across slow network calls.
- Every *kind* of background work needs a **global** concurrency limit, not just a per-user one.
