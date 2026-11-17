"""
Per-turn tool scheduling: concurrent reads, a write barrier.

When the model asks for several tools in one step, ADK already starts them all
at once (``asyncio.gather``). That is right for reads (three web searches take
as long as the slowest one, not the sum) but wrong for side effects:

- Within a step the model planned against the state it had *before* the step,
  so writes must not overlap the reads planned next to them (snapshot
  semantics: reads first, then writes).
- Two writes at once would also mean two confirmation prompts at once, and
  e.g. two image generations hammering the provider.

Rules (a readers-writer lock with a "settle" step):
- read  : shared; at most MAX_PARALLEL_READS at once (politeness to providers)
- write : exclusive; one at a time; waits until the reads of its step finished;
          reads that arrive while a write runs wait for it.

The scheduler is created per request agent (so per turn, per model attempt) and
holds no global state: different users never wait for each other here.
"""
from __future__ import annotations

import asyncio

from app.agent_layer.core.confirmation import CONFIRMATION_REQUIRED

SIDE_EFFECT_TOOLS = CONFIRMATION_REQUIRED
MAX_PARALLEL_READS = 4
# gather() creates all tasks of a step before any of them runs, but a write's
# task may be scheduled first. Yielding a few times lets sibling reads reach
# acquire() and register before the write checks "are reads running?".
SETTLE_YIELDS = 5


def is_write(tool_name: str) -> bool:
    return tool_name in SIDE_EFFECT_TOOLS


class ToolScheduler:
    def __init__(self, max_parallel_reads: int = MAX_PARALLEL_READS):
        self._read_slots = asyncio.Semaphore(max_parallel_reads)
        self._write_lock = asyncio.Lock()
        self._state = asyncio.Condition()
        self._active_reads = 0  # registered reads (running or waiting for a slot)
        self._writing = False
        self._held: dict[str, str] = {}  # call key -> "read" | "write"

    async def acquire(self, key: str, write: bool) -> None:
        if write:
            await self._acquire_write()
        else:
            await self._acquire_read()
        self._held[key] = "write" if write else "read"

    async def release(self, key: str) -> None:
        """Idempotent: after_tool and on_tool_error may both fire for one call."""
        kind = self._held.pop(key, None)
        if kind == "read":
            self._read_slots.release()
            async with self._state:
                self._active_reads -= 1
                self._state.notify_all()
        elif kind == "write":
            async with self._state:
                self._writing = False
                self._state.notify_all()
            self._write_lock.release()

    async def _acquire_read(self) -> None:
        async with self._state:
            await self._state.wait_for(lambda: not self._writing)
            self._active_reads += 1  # registered: a write of this step will wait for us
        try:
            await self._read_slots.acquire()
        except BaseException:
            async with self._state:
                self._active_reads -= 1
                self._state.notify_all()
            raise

    async def _acquire_write(self) -> None:
        for _ in range(SETTLE_YIELDS):
            await asyncio.sleep(0)
        await self._write_lock.acquire()
        try:
            async with self._state:
                await self._state.wait_for(lambda: self._active_reads == 0)
                self._writing = True
        except BaseException:
            self._write_lock.release()
            raise

    @property
    def active_reads(self) -> int:
        return self._active_reads
