"""
Statistics service — time-based analytics and chart data.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from dashboard.core.metrics import metrics

log = logging.getLogger("dashboard.stats")


class StatsService:
    """Aggregates and serves time-based statistics."""

    def __init__(self) -> None:
        self._hourly_sent: dict[int, int] = defaultdict(int)
        self._hourly_failed: dict[int, int] = defaultdict(int)
        self._daily_sent: dict[str, int] = defaultdict(int)
        self._daily_failed: dict[str, int] = defaultdict(int)
        self._scheduler_jobs: list[dict] = []
        self._lock = asyncio.Lock()

    async def record_message(self, success: bool) -> None:
        """Record a message send for time-based stats."""
        now = datetime.now()
        hour_key = now.hour
        day_key = now.strftime("%Y-%m-%d")

        async with self._lock:
            if success:
                self._hourly_sent[hour_key] += 1
                self._daily_sent[day_key] += 1
            else:
                self._hourly_failed[hour_key] += 1
                self._daily_failed[day_key] += 1

    async def get_period_stats(self, period: str) -> dict[str, Any]:
        """Get stats for a time period."""
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")

        async with self._lock:
            if period == "today":
                sent = self._daily_sent.get(today, 0)
                failed = self._daily_failed.get(today, 0)
            elif period == "yesterday":
                yest = (now - timedelta(days=1)).strftime("%Y-%m-%d")
                sent = self._daily_sent.get(yest, 0)
                failed = self._daily_failed.get(yest, 0)
            elif period == "weekly":
                sent = sum(
                    self._daily_sent.get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0)
                    for i in range(7)
                )
                failed = sum(
                    self._daily_failed.get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0)
                    for i in range(7)
                )
            elif period == "monthly":
                sent = sum(
                    self._daily_sent.get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0)
                    for i in range(30)
                )
                failed = sum(
                    self._daily_failed.get((now - timedelta(days=i)).strftime("%Y-%m-%d"), 0)
                    for i in range(30)
                )
            else:  # lifetime
                sent = sum(self._daily_sent.values())
                failed = sum(self._daily_failed.values())

        total = sent + failed
        return {
            "period": period,
            "sent": sent,
            "failed": failed,
            "total": total,
            "success_rate": round((sent / total * 100) if total > 0 else 0, 1),
            "active_accounts": 0,
            "new_logins": 0,
            "flood_waits": 0,
            "bans": 0,
            "retries": 0,
            "queue_processed": total,
            "avg_send_speed": 0,
        }

    async def get_chart_data(self) -> dict[str, Any]:
        """Get chart data for all graphs."""
        async with self._lock:
            # Messages per hour (last 24h)
            hourly_labels = [f"{h:02d}:00" for h in range(24)]
            hourly_sent = [self._hourly_sent.get(h, 0) for h in range(24)]
            hourly_failed = [self._hourly_failed.get(h, 0) for h in range(24)]

            # Daily performance (last 7 days)
            now = datetime.now()
            daily_labels = []
            daily_sent_data = []
            daily_failed_data = []
            for i in range(6, -1, -1):
                day = (now - timedelta(days=i)).strftime("%Y-%m-%d")
                daily_labels.append((now - timedelta(days=i)).strftime("%b %d"))
                daily_sent_data.append(self._daily_sent.get(day, 0))
                daily_failed_data.append(self._daily_failed.get(day, 0))

        mpm = await metrics.get_messages_per_minute()

        return {
            "hourly": {
                "labels": hourly_labels,
                "sent": hourly_sent,
                "failed": hourly_failed,
            },
            "daily": {
                "labels": daily_labels,
                "sent": daily_sent_data,
                "failed": daily_failed_data,
            },
            "messages_per_minute": mpm,
        }

    async def get_scheduler_info(self) -> list[dict[str, Any]]:
        """Get scheduler tasks info."""
        return self._scheduler_jobs

    def update_scheduler_jobs(self, jobs: list[dict]) -> None:
        """Update scheduler jobs from bot."""
        self._scheduler_jobs = jobs


# Global singleton
stats_service = StatsService()
