"""Fan-out of authoritative state to every socket watching a room."""

import asyncio
import logging
from collections import defaultdict

from fastapi import WebSocket
from pydantic import BaseModel

log = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: dict[str, set[WebSocket]] = defaultdict(set)

    def add(self, room_id: str, ws: WebSocket) -> None:
        self._sockets[room_id].add(ws)

    def remove(self, room_id: str, ws: WebSocket) -> None:
        self._sockets.get(room_id, set()).discard(ws)
        if not self._sockets.get(room_id):
            self._sockets.pop(room_id, None)

    def count(self, room_id: str) -> int:
        return len(self._sockets.get(room_id, ()))

    async def send(self, ws: WebSocket, message: BaseModel) -> None:
        await ws.send_text(message.model_dump_json())

    async def broadcast(self, room_id: str, message: BaseModel) -> None:
        """Best-effort fan-out. A dead socket is reaped, never fatal to the sender."""
        targets = list(self._sockets.get(room_id, ()))
        if not targets:
            return

        payload = message.model_dump_json()
        results = await asyncio.gather(
            *(ws.send_text(payload) for ws in targets), return_exceptions=True
        )
        for ws, result in zip(targets, results):
            if isinstance(result, Exception):
                log.debug("dropping dead socket in room %s: %r", room_id, result)
                self.remove(room_id, ws)
