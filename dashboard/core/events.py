"""
Global event bus for real-time communication between bot and dashboard.
Async-safe, zero-blocking publish/subscribe system.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

log = logging.getLogger("dashboard.events")


class EventType(str, Enum):
    # Message events
    MESSAGE_SENT = "message_sent"
    MESSAGE_FAILED = "message_failed"

    # Account events
    ACCOUNT_LOGIN = "account_login"
    ACCOUNT_LOGOUT = "account_logout"
    ACCOUNT_BANNED = "account_banned"
    ACCOUNT_FLOOD = "account_flood"
    ACCOUNT_STATUS = "account_status"
    ACCOUNT_ONLINE = "account_online"

    # System events
    SYSTEM_METRIC = "system_metric"
    TASK_START = "task_start"
    TASK_COMPLETE = "task_complete"
    TASK_FAILED = "task_failed"

    # Scheduler events
    SCHEDULER_RUN = "scheduler_run"
    SCHEDULER_ERROR = "scheduler_error"

    # Log events
    LOG_ENTRY = "log_entry"
    LOG_ERROR = "log_error"

    # Import/Export
    IMPORT_PROGRESS = "import_progress"
    EXPORT_PROGRESS = "export_progress"


@dataclass
class Event:
    type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class EventBus:
    """Async event bus with pub/sub pattern."""

    def __init__(self, max_history: int = 1000) -> None:
        self._subscribers: dict[EventType, list[Callable]] = {}
        self._global_subscribers: list[Callable] = []
        self._history: deque[Event] = deque(maxlen=max_history)
        self._lock = asyncio.Lock()

    def subscribe(self, event_type: EventType, handler: Callable[[Event], Coroutine]) -> None:
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)

    def subscribe_all(self, handler: Callable[[Event], Coroutine]) -> None:
        self._global_subscribers.append(handler)

    async def publish(self, event: Event) -> None:
        self._history.append(event)
        handlers = self._subscribers.get(event.type, []) + self._global_subscribers
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                log.error("Event handler error for %s: %s", event.type, e)

    def get_history(self, event_type: EventType | None = None, limit: int = 100) -> list[Event]:
        if event_type:
            return [e for e in self._history if e.type == event_type][-limit:]
        return list(self._history)[-limit:]


# Global singleton
event_bus = EventBus()
