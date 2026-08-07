"""
Metrics collector — aggregates stats from bot operations.
Provides real-time counters, time-based analytics, and system metrics.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

import psutil

log = logging.getLogger("dashboard.metrics")


class MetricsCollector:
    """Thread-safe metrics collector with time-windowed aggregation."""

    def __init__(self) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._timestamps: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()
        self._lock = asyncio.Lock()

        # Per-minute sliding windows
        self._minute_sent: list[float] = []
        self._minute_failed: list[float] = []

    async def increment(self, key: str, value: int = 1) -> None:
        async with self._lock:
            self._counters[key] += value
            self._timestamps[key].append(time.time())

    async def set_gauge(self, key: str, value: float) -> None:
        async with self._lock:
            self._gauges[key] = value

    async def record_send(self, success: bool) -> None:
        now = time.time()
        async with self._lock:
            if success:
                self._counters["total_sent"] += 1
                self._minute_sent.append(now)
            else:
                self._counters["total_failed"] += 1
                self._minute_failed.append(now)
            # Clean old entries (older than 60s)
            cutoff = now - 60
            self._minute_sent = [t for t in self._minute_sent if t > cutoff]
            self._minute_failed = [t for t in self._minute_failed if t > cutoff]

    async def get_messages_per_minute(self) -> dict[str, int]:
        now = time.time()
        cutoff = now - 60
        async with self._lock:
            self._minute_sent = [t for t in self._minute_sent if t > cutoff]
            self._minute_failed = [t for t in self._minute_failed if t > cutoff]
            return {
                "sent": len(self._minute_sent),
                "failed": len(self._minute_failed),
            }

    async def get_system_metrics(self) -> dict[str, Any]:
        """Get system resource usage (non-blocking via thread)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._collect_system)

    def _collect_system(self) -> dict[str, Any]:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        net = psutil.net_io_counters()
        return {
            "cpu_percent": cpu,
            "ram_used_mb": round(mem.used / 1024 / 1024, 1),
            "ram_total_mb": round(mem.total / 1024 / 1024, 1),
            "ram_percent": mem.percent,
            "disk_used_gb": round(disk.used / 1024 / 1024 / 1024, 2),
            "disk_total_gb": round(disk.total / 1024 / 1024 / 1024, 2),
            "disk_percent": disk.percent,
            "net_sent_mb": round(net.bytes_sent / 1024 / 1024, 2),
            "net_recv_mb": round(net.bytes_recv / 1024 / 1024, 2),
            "uptime_seconds": int(time.time() - self._start_time),
        }

    async def get_overview(self) -> dict[str, Any]:
        async with self._lock:
            total_sent = self._counters.get("total_sent", 0)
            total_failed = self._counters.get("total_failed", 0)
            total = total_sent + total_failed
            return {
                "total_sent": total_sent,
                "total_failed": total_failed,
                "success_rate": round((total_sent / total * 100) if total > 0 else 0, 1),
                "failure_rate": round((total_failed / total * 100) if total > 0 else 0, 1),
                "flood_count": self._counters.get("flood_count", 0),
                "spam_blocks": self._counters.get("spam_blocks", 0),
                "total_tasks": self._counters.get("total_tasks", 0),
                "queue_size": self._counters.get("queue_size", 0),
                "active_schedulers": self._counters.get("active_schedulers", 0),
            }

    async def get_all(self) -> dict[str, Any]:
        overview = await self.get_overview()
        system = await self.get_system_metrics()
        mpm = await self.get_messages_per_minute()
        return {
            **overview,
            "system": system,
            "messages_per_minute": mpm,
        }


# Global singleton
metrics = MetricsCollector()
