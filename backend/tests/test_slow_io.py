"""Sessions give their pooled connection back during slow I/O (real Postgres)."""
import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.db.database import AsyncSessionLocal, engine
from app.db.slow_io import before_slow_io, release_connection_during_slow_io
from app.models import User
from tests.test_compaction import _db_available

pytestmark = [pytest.mark.skipif(not _db_available(), reason="needs the Postgres container"), pytest.mark.asyncio]


def checked_out() -> int:
    return engine.sync_engine.pool.checkedout()


@pytest_asyncio.fixture(autouse=True)
async def fresh_engine():
    await engine.dispose()  # pytest-asyncio: fresh loop per test
    yield
    await engine.dispose()


async def test_read_then_slow_io_returns_the_connection_and_the_session_still_works():
    async with AsyncSessionLocal() as db, release_connection_during_slow_io(db):
        await db.execute(text("select 1"))
        assert db.in_transaction() and checked_out() == 1  # held "idle in transaction"
        await before_slow_io()  # e.g. right before an LLM call
        assert not db.in_transaction() and checked_out() == 0  # back in the pool
        assert (await db.execute(text("select 2"))).scalar() == 2  # next query: a fresh connection


async def test_unflushed_changes_keep_the_transaction():
    async with AsyncSessionLocal() as db, release_connection_during_slow_io(db):
        await db.execute(select(User).limit(1))
        db.add(User(email=f"slowio-{uuid.uuid4().hex[:8]}@example.com", password_hash="x"))
        await before_slow_io()
        assert db.in_transaction() and checked_out() == 1  # nothing committed behind our back
        await db.rollback()


async def test_tasks_spawned_inside_the_job_cannot_release_its_session():
    async with AsyncSessionLocal() as db, release_connection_during_slow_io(db):
        await db.execute(text("select 1"))
        await asyncio.create_task(before_slow_io())  # copies the ContextVar, but isn't the owner
        assert db.in_transaction() and checked_out() == 1


async def test_without_opt_in_nothing_happens():
    async with AsyncSessionLocal() as db:
        await db.execute(text("select 1"))
        await before_slow_io()
        assert db.in_transaction() and checked_out() == 1
