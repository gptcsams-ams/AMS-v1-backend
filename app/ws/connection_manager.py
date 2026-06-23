"""In-memory WebSocket connection manager (Redis-free pub/sub substitute)."""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # user_id -> set of WebSocket connections
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, user_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[user_id].add(websocket)
        log.info("WS connected user=%s total=%d", user_id,
                 len(self._connections[user_id]))

    def disconnect(self, user_id: str, websocket: WebSocket) -> None:
        self._connections[user_id].discard(websocket)
        if not self._connections[user_id]:
            del self._connections[user_id]

    async def send_to_user(self, user_id: str, payload: dict) -> None:
        """Push a JSON payload to all sockets for user_id."""
        dead: list[WebSocket] = []
        for ws in list(self._connections.get(user_id, [])):
            try:
                await ws.send_text(json.dumps(payload))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_to_users(self, user_ids: list[str], payload: dict) -> None:
        await asyncio.gather(
            *(self.send_to_user(uid, payload) for uid in user_ids),
            return_exceptions=True,
        )


# Singleton used across the app
notification_manager = ConnectionManager()
