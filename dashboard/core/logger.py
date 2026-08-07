"""
Real-time log capture and streaming system.
Captures Python logging output and forwards to WebSocket clients.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class LogLevel(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class LogCategory(str, Enum):
    LOGIN = "login"
    SEND = "send"
    FAILED = "failed"
    ERROR = "error"
    FLOOD = "flood"
    SCHEDULER = "scheduler"
    JOIN_LEAVE = "join_leave"
    PROXY = "proxy"
    SESSION = "session"
    RETRY = "retry"
    SYSTEM = "system"
    IMPORT = "import"
    EXPORT = "export"


@dataclass
class LogEntry:
    level: str
    category: str
    message: str
    timestamp: float = field(default_factory=time.time)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "timestamp": self.timestamp,
            "extra": self.extra,
        }


class LogBuffer:
    """Ring buffer for log entries with real-time streaming."""

    def __init__(self, max_size: int = 5000) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=max_size)
        self._subscribers: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()

    async def add(self, entry: LogEntry) -> None:
        async with self._lock:
            self._entries.append(entry)
            # Push to all subscriber queues
            dead_queues = []
            for q in self._subscribers:
                try:
                    q.put_nowait(entry)
                except asyncio.QueueFull:
                    dead_queues.append(q)
            for q in dead_queues:
                self._subscribers.remove(q)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def get_recent(self, limit: int = 100, category: str | None = None, level: str | None = None) -> list[dict]:
        entries = list(self._entries)
        if category:
            entries = [e for e in entries if e.category == category]
        if level:
            entries = [e for e in entries if e.level == level]
        return [e.to_dict() for e in entries[-limit:]]

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)


# Global log buffer
log_buffer = LogBuffer()


class DashboardLogHandler(logging.Handler):
    """Custom logging handler that captures logs to the dashboard buffer."""

    CATEGORY_KEYWORDS = {
        LogCategory.LOGIN: ["login", "auth", "otp", "code", "phone"],
        LogCategory.SEND: ["sent", "sending", "broadcast", "forward"],
        LogCategory.FAILED: ["failed", "failure", "error sending"],
        LogCategory.FLOOD: ["flood", "FloodWait", "rate limit"],
        LogCategory.SCHEDULER: ["scheduler", "cron", "schedule", "job"],
        LogCategory.JOIN_LEAVE: ["join", "leave", "group", "channel"],
        LogCategory.PROXY: ["proxy", "socks", "http_proxy"],
        LogCategory.SESSION: ["session", "disconnect", "reconnect", "connect"],
        LogCategory.RETRY: ["retry", "attempt", "reconnect"],
        LogCategory.IMPORT: ["import", "upload", "bulk"],
        LogCategory.EXPORT: ["export", "download"],
    }

    def __init__(self) -> None:
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None

    def _detect_category(self, message: str) -> str:
        msg_lower = message.lower()
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in msg_lower for kw in keywords):
                return cat.value
        return LogCategory.SYSTEM.value

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            entry = LogEntry(
                level=record.levelname.lower(),
                category=self._detect_category(message),
                message=message,
                extra={"logger": record.name, "module": record.module},
            )
            # Schedule async add if we have a running loop
            loop = self._loop
            if loop is None or loop.is_closed():
                try:
                    loop = asyncio.get_running_loop()
                    self._loop = loop
                except RuntimeError:
                    return

            if loop.is_running():
                loop.create_task(log_buffer.add(entry))
        except Exception:
            pass  # Never block the logging system


# Install the handler
dashboard_handler = DashboardLogHandler()
dashboard_handler.setLevel(logging.DEBUG)
dashboard_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-8s %(name)s — %(message)s"))
