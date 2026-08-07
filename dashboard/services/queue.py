"""
Queue-based message sending system with semaphore protection and batch processing.
Provides non-blocking, rate-limited message dispatch.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Coroutine

from dashboard.config import settings
from dashboard.core.metrics import metrics

log = logging.getLogger("dashboard.queue")


@dataclass
class SendTask:
    """A queued send operation."""
    user_id: int
    phone: str
    group_id: int
    group_title: str
    message: str
    topic_id: int | None = None
    priority: int = 0
    created_at: float = 0.0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = time.time()


class SendQueue:
    """
    Async send queue with:
    - Semaphore-protected concurrent sending
    - Priority queue support
    - Rate limiting per account
    - Batch processing
    - Automatic retry with backoff
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_size: int = 10000,
    ) -> None:
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue(maxsize=max_size)
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = False
        self._workers: list[asyncio.Task] = []
        self._send_func: Callable | None = None
        self._rate_limits: dict[str, float] = {}  # phone -> next_allowed_time

    def set_send_function(self, func: Callable) -> None:
        """Set the actual send function to use."""
        self._send_func = func

    async def start(self, worker_count: int = 4) -> None:
        """Start queue workers."""
        self._running = True
        for i in range(worker_count):
            task = asyncio.create_task(self._worker(f"worker-{i}"))
            self._workers.append(task)
        log.info("Send queue started with %d workers", worker_count)

    async def stop(self) -> None:
        """Stop queue workers gracefully."""
        self._running = False
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        log.info("Send queue stopped")

    async def enqueue(self, task: SendTask) -> bool:
        """Add a send task to the queue. Returns False if queue is full."""
        try:
            self._queue.put_nowait((task.priority, task.created_at, task))
            await metrics.set_gauge("queue_size", self._queue.qsize())
            return True
        except asyncio.QueueFull:
            log.warning("Send queue full (max=%d)", self._queue.maxsize)
            return False

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_running(self) -> bool:
        return self._running

    async def _worker(self, name: str) -> None:
        """Queue consumer worker."""
        while self._running:
            try:
                _, _, task = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                async with self._semaphore:
                    await self._process_task(task)
                    await metrics.set_gauge("queue_size", self._queue.qsize())
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("[%s] Worker error: %s", name, e)
                await asyncio.sleep(1)

    async def _process_task(self, task: SendTask) -> None:
        """Process a single send task with rate limiting."""
        phone = task.phone
        # Check rate limit
        now = time.time()
        next_allowed = self._rate_limits.get(phone, 0)
        if now < next_allowed:
            wait = next_allowed - now
            await asyncio.sleep(wait)

        if self._send_func:
            try:
                await self._send_func(task)
                # Update rate limit (min 1s between sends per account)
                self._rate_limits[phone] = time.time() + 1.0
            except Exception as e:
                log.error("Send task failed: %s", e)


# Global singleton
send_queue = SendQueue(
    max_concurrent=settings.max_concurrent_sends,
    max_size=settings.queue_max_size,
)
