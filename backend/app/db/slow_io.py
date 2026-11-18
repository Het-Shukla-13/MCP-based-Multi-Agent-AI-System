"""
Give a pooled DB connection back while waiting on slow network calls.

An AsyncSession takes a pool connection at its first query and keeps it until the
transaction ends. Background jobs that read, then call an LLM or the embedding
API for seconds, then write, used to hold that connection - "idle in transaction"
- the whole time; enough of them starved the pool for user requests (note 47).

Usage (the job opts in for ITS session):

    async with AsyncSessionLocal() as db, release_connection_during_slow_io(db):
        ...  # any LLM/embedding call below first ends db's transaction

The LLM and embedding wrappers call `before_slow_io()`; with no opt-in it does
nothing. Safe because:
- sessions use expire_on_commit=False, so loaded objects stay usable;
- it COMMITS (never rolls back): flushed writes are kept, never lost; with
  unflushed pending changes it leaves the transaction alone (logged);
- it only acts in the task that opted in: tasks spawned from inside the job copy
  the ContextVar, and must not commit someone else's session.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import Awaitable, Callable

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

_release_hook: ContextVar[Callable[[], Awaitable[None]] | None] = ContextVar("slow_io_release", default=None)


@asynccontextmanager
async def release_connection_during_slow_io(db: AsyncSession):
    owner = asyncio.current_task()

    async def release() -> None:
        if asyncio.current_task() is not owner or not db.in_transaction():
            return
        if db.new or db.dirty or db.deleted:
            logger.debug("Slow I/O: session has unflushed changes; keeping its connection")
            return
        await db.commit()  # ends the transaction -> the connection returns to the pool

    token = _release_hook.set(release)
    try:
        yield db
    finally:
        _release_hook.reset(token)


async def before_slow_io() -> None:
    """Call right before a slow network call (LLM, embeddings)."""
    hook = _release_hook.get()
    if hook is not None:
        await hook()
