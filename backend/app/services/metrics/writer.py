"""
Non-blocking metrics writer (producer/consumer).

Producers (the chat turn, agent events, LLM calls in thread pools) call put(),
which only appends to a thread-safe queue: no database work on the reply path.
One consumer task drains the queue every FLUSH_SECONDS and inserts a batch in a
single transaction. Metrics are best-effort: a failed write is logged, never raised.
"""

import asyncio
import queue

from loguru import logger

FLUSH_SECONDS = 0.5
MAX_BATCH = 500


class MetricsWriter:
    def __init__(self) -> None:
        self._queue: "queue.SimpleQueue[tuple[str, dict]]" = queue.SimpleQueue()  # thread-safe
        self._task: asyncio.Task | None = None

    def put(self, kind: str, row: dict) -> None:
        self._queue.put((kind, row))

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run(), name="metrics-writer")

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            self._task = None
        await self.flush()  # don't lose the last batch on shutdown

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(FLUSH_SECONDS)
            await self.flush()

    def _drain(self) -> list[tuple[str, dict]]:
        items = []
        while len(items) < MAX_BATCH:
            try:
                items.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return items

    async def flush(self) -> int:
        items = self._drain()
        if not items:
            return 0
        from app.db.database import AsyncSessionLocal
        from app.models.metrics import LlmCall, TurnMetric

        model_for = {"turn": TurnMetric, "llm_call": LlmCall}
        try:
            async with AsyncSessionLocal() as db:
                db.add_all([model_for[kind](**row) for kind, row in items])
                await db.commit()
        except Exception:
            logger.exception("Metrics write failed; dropped {} rows", len(items))
        return len(items)


metrics_writer = MetricsWriter()
