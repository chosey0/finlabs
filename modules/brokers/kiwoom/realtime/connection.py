from __future__ import annotations

import asyncio
import json
from typing import Any

from modules.brokers.kiwoom._internal.headers import (
    build_websocket_login_message,
    build_websocket_subscription_message,
)
from modules.brokers.kiwoom.config import websocket_url
from modules.brokers.kiwoom.exceptions import KiwoomRealtimeError
from modules.brokers.kiwoom.realtime.subscription import RealtimeSubscription
from modules.brokers.kiwoom.types import Environment

_WEBSOCKET_PATH = "/api/dostk/websocket"


class KiwoomRealtimeConnection:
    def __init__(
        self,
        *,
        environment: Environment,
        access_token: str,
        connect_timeout_seconds: float = 10.0,
    ) -> None:
        self.environment = environment
        self.access_token = access_token
        self.connect_timeout_seconds = connect_timeout_seconds
        self.url = f"{websocket_url(environment)}{_WEBSOCKET_PATH}"
        self._socket: Any | None = None

    @property
    def is_connected(self) -> bool:
        return self._socket is not None

    async def connect(self) -> None:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - dependency is env-specific
            raise KiwoomRealtimeError(
                "Kiwoom realtime requires the `websockets` package"
            ) from exc

        self._socket = await websockets.connect(
            self.url,
            open_timeout=self.connect_timeout_seconds,
        )
        await self.send_json(build_websocket_login_message(access_token=self.access_token))
        await self._wait_for_login()

    async def close(self) -> None:
        if self._socket is not None:
            await self._socket.close()
            self._socket = None

    async def recv(self) -> str:
        if self._socket is None:
            raise KiwoomRealtimeError("Kiwoom realtime socket is not connected")
        frame = await self._socket.recv()
        if isinstance(frame, bytes):
            return frame.decode("utf-8")
        return str(frame)

    async def send_text(self, text: str) -> None:
        if self._socket is None:
            raise KiwoomRealtimeError("Kiwoom realtime socket is not connected")
        await self._socket.send(text)

    async def send_json(self, payload: dict[str, object]) -> None:
        await self.send_text(json.dumps(payload, ensure_ascii=False))

    async def send_subscription(
        self,
        subscription: RealtimeSubscription,
        *,
        trnm: str = "REG",
        group_no: str = "1",
        refresh: bool = True,
    ) -> None:
        await self.send_json(
            build_websocket_subscription_message(
                tr_id=subscription.tr_id,
                tr_key=subscription.tr_key,
                trnm=trnm,
                group_no=group_no,
                refresh=refresh,
            )
        )

    async def _wait_for_login(self) -> None:
        while True:
            frame = await asyncio.wait_for(
                self.recv(),
                timeout=self.connect_timeout_seconds,
            )
            payload = _json_object(frame)
            trnm = str(payload.get("trnm") or "").strip()
            if trnm == "PING":
                await self.send_text(frame)
                continue
            if trnm != "LOGIN":
                continue
            return_code = str(payload.get("return_code") or "").strip()
            if return_code not in {"", "0"}:
                return_msg = str(payload.get("return_msg") or "").strip()
                raise KiwoomRealtimeError(
                    f"Kiwoom realtime login failed: {return_code} {return_msg}"
                )
            return


def _json_object(frame: str) -> dict[str, Any]:
    try:
        payload = json.loads(frame)
    except json.JSONDecodeError as exc:
        raise KiwoomRealtimeError("Kiwoom realtime frame was not valid JSON") from exc
    if not isinstance(payload, dict):
        raise KiwoomRealtimeError("Kiwoom realtime frame must be a JSON object")
    return payload
