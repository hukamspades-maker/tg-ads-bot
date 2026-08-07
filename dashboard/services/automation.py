"""
Smart automation service — auto-reconnect, retry, spam detection, load balancing.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from dashboard.core.events import Event, EventType, event_bus
from dashboard.core.metrics import metrics

log = logging.getLogger("dashboard.automation")


class SmartAutomation:
    """Background automation that monitors and self-heals account issues."""

    def __init__(self) -> None:
        self._running = False
        self._task: asyncio.Task | None = None
        self._bot_ref = None
        self._flood_tracker: dict[str, float] = {}  # phone -> flood_until
        self._spam_tracker: dict[str, int] = {}  # phone -> consecutive_fails
        self._reconnect_queue: asyncio.Queue = asyncio.Queue()

    def set_bot_reference(self, bot_module: Any) -> None:
        self._bot_ref = bot_module

    async def start(self) -> None:
        """Start automation background tasks."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        log.info("Smart automation started")

    async def stop(self) -> None:
        """Stop automation."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=3.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass

    async def _monitor_loop(self) -> None:
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_flood_recovery()
                await self._check_dead_sessions()
                await self._update_account_stats()
            except Exception as e:
                log.error("Automation monitor error: %s", e)
            await asyncio.sleep(30)

    async def _check_flood_recovery(self) -> None:
        """Check if flood-waited accounts can be resumed."""
        now = time.time()
        recovered = []
        for phone, until in list(self._flood_tracker.items()):
            if now >= until:
                recovered.append(phone)
                log.info("[Automation] Account %s flood wait recovered", phone)
                await event_bus.publish(Event(
                    type=EventType.ACCOUNT_STATUS,
                    data={"phone": phone, "status": "active", "event": "flood_recovered"},
                ))
        for phone in recovered:
            del self._flood_tracker[phone]

    async def _check_dead_sessions(self) -> None:
        """Check for disconnected sessions and attempt reconnect."""
        if not self._bot_ref:
            return
        try:
            user_manager = self._bot_ref.UserManager
            for uid in user_manager.get_all_user_ids():
                mgr = user_manager.get_account_mgr(uid)
                for acc in mgr.get_accounts():
                    phone = acc["phone"]
                    client = mgr._clients.get(phone)
                    if client and not client.is_connected():
                        log.info("[Automation] Reconnecting dead session: %s", phone)
                        try:
                            await client.connect()
                            await event_bus.publish(Event(
                                type=EventType.ACCOUNT_STATUS,
                                data={"phone": phone, "status": "active", "event": "reconnected"},
                            ))
                        except Exception as e:
                            log.warning("[Automation] Reconnect failed for %s: %s", phone, e)
        except Exception as e:
            log.error("[Automation] Dead session check error: %s", e)

    async def _update_account_stats(self) -> None:
        """Update account online/offline status for dashboard."""
        if not self._bot_ref:
            return
        try:
            user_manager = self._bot_ref.UserManager
            online_count = 0
            for uid in user_manager.get_all_user_ids():
                mgr = user_manager.get_account_mgr(uid)
                for acc in mgr.get_accounts():
                    phone = acc["phone"]
                    client = mgr._clients.get(phone)
                    if client and client.is_connected():
                        online_count += 1
            await metrics.set_gauge("online_accounts", online_count)
        except Exception:
            pass

    def record_flood(self, phone: str, wait_seconds: int) -> None:
        """Record a flood wait event."""
        self._flood_tracker[phone] = time.time() + wait_seconds

    def record_failure(self, phone: str) -> None:
        """Track consecutive failures for spam detection."""
        self._spam_tracker[phone] = self._spam_tracker.get(phone, 0) + 1
        if self._spam_tracker[phone] >= 5:
            log.warning("[Automation] Possible spam block detected for %s (%d consecutive failures)",
                        phone, self._spam_tracker[phone])

    def record_success(self, phone: str) -> None:
        """Reset failure counter on success."""
        self._spam_tracker.pop(phone, None)


# Global singleton
automation = SmartAutomation()
