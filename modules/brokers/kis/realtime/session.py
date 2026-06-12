from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from modules.brokers.kis.realtime.connection import RealtimeConnection
from modules.brokers.kis.realtime.frame import RealtimeFrameProcessor, is_pingpong_frame
from modules.brokers.kis.realtime.subscription import (
    Feed,
    RealtimeSubscription,
    SubscriptionRegistry,
    subscription_for,
)

if TYPE_CHECKING:
    from modules.brokers.kis.client import KisClient

logger = logging.getLogger(__name__)


class RealtimeSession:
    def __init__(self, client: "KisClient") -> None:
        self._client = client
        self._connection: RealtimeConnection | None = None
        self._registry = SubscriptionRegistry()
        self._frame_processor = RealtimeFrameProcessor(self._registry)

    @property
    def subscriptions(self) -> frozenset[RealtimeSubscription]:
        return self._registry.subscriptions

    async def __aenter__(self) -> "RealtimeSession":
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def subscribe_trades(
        self,
        symbol: str,
        market_or_exchange: str | None = None,
        *,
        market: str | None = None,
        exchange: str | None = None,
        feed: Feed | None = None,
    ) -> RealtimeSubscription:
        venue = market_or_exchange or market or exchange
        if not venue:
            raise ValueError("market or exchange must be provided")
        return await self._subscribe(
            channel="trades",
            symbol=symbol,
            venue=venue,
            feed=feed,
            tr_type="1",
        )

    async def subscribe_orderbook(
        self,
        symbol: str,
        market_or_exchange: str | None = None,
        *,
        market: str | None = None,
        exchange: str | None = None,
        feed: Feed | None = None,
    ) -> RealtimeSubscription:
        venue = market_or_exchange or market or exchange
        if not venue:
            raise ValueError("market or exchange must be provided")
        return await self._subscribe(
            channel="orderbook",
            symbol=symbol,
            venue=venue,
            feed=feed,
            tr_type="1",
        )

    async def unsubscribe(
        self,
        subscription: RealtimeSubscription | str,
        *,
        channel: str = "trades",
        market: str | None = None,
        exchange: str | None = None,
        feed: Feed | None = None,
    ) -> None:
        if isinstance(subscription, RealtimeSubscription):
            target = subscription
        else:
            venue = market or exchange
            if not venue:
                raise ValueError("market or exchange must be provided")
            target = subscription_for(
                channel=channel,
                symbol=subscription,
                venue=venue,
                feed=feed,
                environment=self._client.environment,
            )
        await self._send_subscription(target, tr_type="2")
        self._registry.discard(target)

    async def stream(self):
        while True:
            if self._connection is None or not self._connection.is_connected:
                await self._connect()
                await self._resubscribe()
            try:
                frame = await self._connection.recv()
            except Exception:
                logger.warning("realtime websocket disconnected; reconnecting")
                await self._disconnect()
                continue
            if not isinstance(frame, str):
                logger.warning("ignored non-text realtime websocket frame")
                continue
            if is_pingpong_frame(frame):
                await self._connection.send_text(frame)
                continue
            for event in self._frame_processor.process(frame):
                yield event

    async def _connect(self) -> None:
        approval_key = await self._client.ensure_approval_key()
        self._connection = RealtimeConnection(
            environment=self._client.environment,
            approval_key=approval_key,
        )
        await self._connection.connect()

    async def _disconnect(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _subscribe(
        self,
        *,
        channel: str,
        symbol: str,
        venue: str,
        feed: Feed | None,
        tr_type: str,
    ) -> RealtimeSubscription:
        subscription = subscription_for(
            channel=channel,
            symbol=symbol,
            venue=venue,
            feed=feed,
            environment=self._client.environment,
        )
        await self._send_subscription(subscription, tr_type=tr_type)
        self._registry.add(subscription)
        return subscription

    async def _send_subscription(
        self,
        subscription: RealtimeSubscription,
        *,
        tr_type: str,
    ) -> None:
        if self._connection is None:
            raise RuntimeError("RealtimeSession must be used as an async context manager")
        await self._connection.send_subscription(subscription, tr_type=tr_type)

    async def _resubscribe(self) -> None:
        for subscription in self._registry.all():
            await self._send_subscription(subscription, tr_type="1")
