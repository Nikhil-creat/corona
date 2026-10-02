from __future__ import annotations

import asyncio
import json
import logging

from fastapi import WebSocket

log = logging.getLogger(__name__)


class ConnectionHub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    def __len__(self) -> int:
        return len(self._clients)

    async def add(self, ws: WebSocket) -> None:
        await ws.accept()
        self._clients.add(ws)

    def remove(self, ws: WebSocket) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        raw = json.dumps(message)
        results = await asyncio.gather(*(c.send_text(raw) for c in list(self._clients)), return_exceptions=True)
        for client, res in zip(list(self._clients), results):
            if isinstance(res, Exception):
                self._clients.discard(client)
