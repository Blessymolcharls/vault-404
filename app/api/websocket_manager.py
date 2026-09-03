"""WebSocket Hub & Broadcast Connection Manager for The Inconvenient Vault."""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Set, Union
from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger("vault.api.websocket")


class WebSocketManager:
    """Thread/async-safe connection manager maintaining active client WebSockets and broadcasting telemetry."""

    def __init__(self) -> None:
        """Initialize the WebSocket connection manager."""
        self._active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def active_count(self) -> int:
        """Return the number of currently connected WebSocket clients."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new incoming client WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info(f"WebSocket client connected. Total active: {len(self._active_connections)}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected client WebSocket."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active: {len(self._active_connections)}")

    async def broadcast_event(self, event_type: str, data: Union[Dict[str, Any], BaseModel]) -> None:
        """Format and broadcast a JSON message payload to all active client streams."""
        payload_data = data.model_dump() if isinstance(data, BaseModel) else data
        message = {
            "event": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload_data,
        }
        await self.broadcast_json(message)

    async def broadcast_json(self, message: Dict[str, Any]) -> None:
        """Send a JSON dictionary payload to all connected clients, purging dead sockets."""
        async with self._lock:
            connections = list(self._active_connections)

        if not connections:
            return

        json_str = json.dumps(message, default=str)
        dead_connections: List[WebSocket] = []

        for ws in connections:
            try:
                await ws.send_text(json_str)
            except Exception as ex:
                logger.debug(f"Failed to send to WebSocket client ({ex}). Marking dead.")
                dead_connections.append(ws)

        if dead_connections:
            async with self._lock:
                for dead_ws in dead_connections:
                    self._active_connections.discard(dead_ws)
            logger.info(f"Purged {len(dead_connections)} dead WebSocket connection(s).")
