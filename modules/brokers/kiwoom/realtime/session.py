from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from modules.brokers.kiwoom.realtime.connection import KiwoomRealtimeConnection
from modules.brokers.kiwoom.realtime.frame import RealtimeEvent, RealtimeFrameProcessor
from modules.brokers.kiwoom.realtime.subscription import (
    RealtimeSubscription,
    SubscriptionRegistry,
    subscription_for,
)

if TYPE_CHECKING:
    from modules.brokers.kiwoom.client import KiwoomClient


@dataclass
class RealtimeSession:
    client: "KiwoomClient"
    reconnect: bool = True
    reconnect_delay_seconds: float = 1.0
    _connection: KiwoomRealtimeConnection | None = field(
        default=None,
        init=False,
        repr=False,
    )
    _subscriptions: SubscriptionRegistry = field(
        default_factory=SubscriptionRegistry,
        init=False,
        repr=False,
    )
    _processor: RealtimeFrameProcessor = field(init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self._processor = RealtimeFrameProcessor(self._subscriptions)

    async def __aenter__(self) -> "RealtimeSession":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(self) -> None:
        token = await self.client.ensure_token()
        self._connection = KiwoomRealtimeConnection(
            environment=self.client.environment,
            access_token=token,
        )
        await self._connection.connect()
        for subscription in self._subscriptions.all():
            await self._connection.send_subscription(subscription)

    async def close(self) -> None:
        self._closed = True
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def subscribe_trades(
        self,
        symbol: str,
        *,
        market: str = "KRX",
    ) -> RealtimeSubscription:
        return await self._subscribe(subscription_for("trades", symbol, market=market))

    async def subscribe_orderbook(
        self,
        symbol: str,
        *,
        market: str = "KRX",
    ) -> RealtimeSubscription:
        return await self._subscribe(subscription_for("orderbook", symbol, market=market))

    async def unsubscribe(
        self,
        subscription_or_symbol: RealtimeSubscription | str,
        *,
        channel: str = "trades",
        market: str = "KRX",
    ) -> RealtimeSubscription:
        if isinstance(subscription_or_symbol, RealtimeSubscription):
            subscription = subscription_or_symbol
        else:
            subscription = subscription_for(
                channel,
                subscription_or_symbol,
                market=market,
            )
        if self._connection is not None:
            await self._connection.send_subscription(subscription, trnm="REMOVE")
        self._subscriptions.remove(subscription)
        return subscription

    async def stream(self) -> AsyncIterator[RealtimeEvent]:
        while not self._closed:
            await self._ensure_connected()
            try:
                if self._connection is None:
                    continue
                frame = await self._connection.recv()
                if _is_ping(frame):
                    await self._connection.send_text(frame)
                    continue
            except Exception:
                if not self.reconnect or self._closed:
                    raise
                if self._connection is not None:
                    await self._connection.close()
                    self._connection = None
                await asyncio.sleep(self.reconnect_delay_seconds)
                continue
            for event in self._processor.process(frame):
                yield event

    async def _subscribe(
        self,
        subscription: RealtimeSubscription,
    ) -> RealtimeSubscription:
        self._subscriptions.add(subscription)
        if self._connection is not None:
            await self._connection.send_subscription(subscription)
        return subscription

    async def _ensure_connected(self) -> None:
        if self._connection is None or not self._connection.is_connected:
            await self.connect()


def _is_ping(frame: str) -> bool:
    from modules.brokers.kiwoom.realtime.frame import is_ping_frame

    return is_ping_frame(frame)
