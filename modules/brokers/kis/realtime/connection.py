from __future__ import annotations

import json

import websockets

from modules.brokers.kis._internal.headers import build_websocket_subscribe_message
from modules.brokers.kis.config import websocket_url
from modules.brokers.kis.realtime.subscription import RealtimeSubscription
from modules.brokers.kis.types import Environment


class RealtimeConnection:
    """WebSocket lifecycle and subscribe-message transport."""

    def __init__(self, *, environment: Environment, approval_key: str) -> None:
        self._environment = environment
        self._approval_key = approval_key
        self._websocket = None

    @property
    def is_connected(self) -> bool:
        return self._websocket is not None

    async def connect(self) -> None:
        self._websocket = await websockets.connect(websocket_url(self._environment))

    async def close(self) -> None:
        if self._websocket is None:
            return
        close = getattr(self._websocket, "close", None)
        if close is not None:
            result = close()
            if hasattr(result, "__await__"):
                await result
        self._websocket = None

    async def recv(self) -> str:
        if self._websocket is None:
            raise RuntimeError("RealtimeConnection is not connected")
        return await self._websocket.recv()

    async def send_subscription(
        self,
        subscription: RealtimeSubscription,
        *,
        tr_type: str,
    ) -> None:
        if self._websocket is None:
            raise RuntimeError("RealtimeConnection is not connected")
        message = build_websocket_subscribe_message(
            approval_key=self._approval_key,
            tr_id=subscription.tr_id,
            tr_key=subscription.tr_key,
            tr_type=tr_type,
        )
        await self._websocket.send(json.dumps(message, ensure_ascii=False))
