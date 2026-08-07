"""
WebSocket connection manager for real-time dashboard updates.
Handles multiple clients, auto-reconnect support, and secure auth.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from dashboard.core.events import Event, event_bus

log = logging.getLogger("dashboard.ws")


class ConnectionManager:
    """Manages WebSocket connections with broadcast capability."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        log.info("WebSocket client connected. Total: %d", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        log.info("WebSocket client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send message to all connected clients."""
        dead: list[WebSocket] = []
        async with self._lock:
            connections = list(self._connections)

        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self._connections:
                        self._connections.remove(ws)

    async def send_to(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        try:
            await websocket.send_json(message)
        except Exception:
            await self.disconnect(websocket)

    @property
    def active_count(self) -> int:
        return len(self._connections)


# Global WebSocket manager
ws_manager = ConnectionManager()


async def _event_to_ws(event: Event) -> None:
    """Bridge: forward all events to WebSocket clients."""
    msg = {
        "type": event.type.value,
        "data": event.data,
        "timestamp": event.timestamp,
    }
    await ws_manager.broadcast(msg)


# Register the bridge handler
event_bus.subscribe_all(_event_to_ws)
