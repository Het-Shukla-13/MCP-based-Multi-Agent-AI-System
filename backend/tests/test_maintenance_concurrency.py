"""Background maintenance must never take more than N DB sessions at once."""
import asyncio
from uuid import uuid4

import pytest

import app.services.memory.background_memory_pipeline as pipeline
from app.core.config import settings


class Tracker:
    active = 0
    peak = 0


class FakeSession:
    async def __aenter__(self):
        Tracker.active += 1
        Tracker.peak = max(Tracker.peak, Tracker.active)
        await asyncio.sleep(0.05)  # "slow LLM call while holding the connection"
        return self

    async def __aexit__(self, *exc):
        Tracker.active -= 1
        return False

    def __getattr__(self, name):  # any DB call inside the pipeline fails fast (caught + logged)
        raise RuntimeError("fake session")


@pytest.mark.asyncio
async def test_pipelines_across_many_users_share_a_small_pool_of_slots(monkeypatch):
    Tracker.active = Tracker.peak = 0
    monkeypatch.setattr(pipeline, "AsyncSessionLocal", FakeSession)
    users = [uuid4() for _ in range(6)]  # six different users: per-user locks don't serialise them
    await asyncio.gather(*(pipeline.run_memory_maintenance_pipeline(user_id=u, conversation_id=uuid4()) for u in users))
    assert Tracker.peak == settings.MAINTENANCE_MAX_CONCURRENT_RUNS
    assert Tracker.active == 0
