from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import websockets

from kis._internal.headers import build_websocket_subscribe_message
from kis.config import websocket_url
from kis.endpoints.registry import lookup
from kis.exceptions import KisRealtimeError
from kis.models.orderbook import OrderBookSnapshot
from kis.models.tick import RealtimeTick
from kis.parsers.realtime import parse_realtime_frame

if TYPE_CHECKING:
    from kis.client import KisClient

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RealtimeSubscription:
    channel: str
    tr_id: str
    tr_key: str
    market: str
    symbol: str


class RealtimeSession:
    def __init__(self, client: "KisClient") -> None:
        self._client = client
        self._approval_key = ""
        self._websocket = None
        self._subscriptions: set[RealtimeSubscription] = set()
        self._received_seq = 0

    @property
    def subscriptions(self) -> frozenset[RealtimeSubscription]:
        return frozenset(self._subscriptions)

    async def __aenter__(self) -> "RealtimeSession":
        self._approval_key = await self._client.ensure_approval_key()
        await self._connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._websocket is not None:
            close = getattr(self._websocket, "close", None)
            if close is not None:
                result = close()
                if hasattr(result, "__await__"):
                    await result
            self._websocket = None

    async def subscribe_trades(
        self,
        symbol: str,
        market_or_exchange: str | None = None,
        *,
        market: str | None = None,
        exchange: str | None = None,
    ) -> RealtimeSubscription:
        venue = market_or_exchange or market or exchange
        if not venue:
            raise ValueError("market or exchange must be provided")
        return await self._subscribe(
            channel="trades",
            symbol=symbol,
            venue=venue,
            tr_type="1",
        )

    async def subscribe_orderbook(
        self,
        symbol: str,
        market_or_exchange: str | None = None,
        *,
        market: str | None = None,
        exchange: str | None = None,
    ) -> RealtimeSubscription:
        venue = market_or_exchange or market or exchange
        if not venue:
            raise ValueError("market or exchange must be provided")
        return await self._subscribe(
            channel="orderbook",
            symbol=symbol,
            venue=venue,
            tr_type="1",
        )

    async def unsubscribe(
        self,
        subscription: RealtimeSubscription | str,
        *,
        channel: str = "trades",
        market: str | None = None,
        exchange: str | None = None,
    ) -> None:
        if isinstance(subscription, RealtimeSubscription):
            target = subscription
        else:
            venue = market or exchange
            if not venue:
                raise ValueError("market or exchange must be provided")
            target = _subscription_for(
                channel=channel, symbol=subscription, venue=venue
            )
        await self._send_subscription(target, tr_type="2")
        self._subscriptions.discard(target)

    async def stream(self):
        while True:
            if self._websocket is None:
                await self._connect()
                await self._resubscribe()
            try:
                frame = await self._websocket.recv()
            except Exception:
                logger.warning("realtime websocket disconnected; reconnecting")
                self._websocket = None
                continue
            if not isinstance(frame, str):
                logger.warning("ignored non-text realtime websocket frame")
                continue
            if frame.lstrip().startswith("{"):
                self._handle_ack(frame)
                continue
            received_seq_start = self._received_seq + 1
            events = parse_realtime_frame(
                frame,
                received_seq_start=received_seq_start,
            )
            self._received_seq += len(events)
            for event in events:
                self._validate_event(event)
                yield event

    async def _subscribe(
        self,
        *,
        channel: str,
        symbol: str,
        venue: str,
        tr_type: str,
    ) -> RealtimeSubscription:
        subscription = _subscription_for(channel=channel, symbol=symbol, venue=venue)
        await self._send_subscription(subscription, tr_type=tr_type)
        self._subscriptions.add(subscription)
        return subscription

    async def _send_subscription(
        self,
        subscription: RealtimeSubscription,
        *,
        tr_type: str,
    ) -> None:
        if self._websocket is None:
            raise RuntimeError(
                "RealtimeSession must be used as an async context manager"
            )
        message = build_websocket_subscribe_message(
            approval_key=self._approval_key,
            tr_id=subscription.tr_id,
            tr_key=subscription.tr_key,
            tr_type=tr_type,
        )
        await self._websocket.send(json.dumps(message, ensure_ascii=False))

    async def _connect(self) -> None:
        self._websocket = await websockets.connect(
            websocket_url(self._client.environment)
        )

    async def _resubscribe(self) -> None:
        for subscription in tuple(self._subscriptions):
            await self._send_subscription(subscription, tr_type="1")

    def _handle_ack(self, frame: str) -> None:
        try:
            payload = json.loads(frame)
        except json.JSONDecodeError:
            logger.warning("ignored malformed realtime JSON frame")
            return
        msg = str(payload.get("body", {}).get("msg1", ""))
        if msg and "SUCCESS" not in msg:
            logger.warning("realtime websocket control message: %s", msg)

    def _validate_event(self, event: RealtimeTick | OrderBookSnapshot) -> None:
        if not any(
            subscription.tr_id == event.tr_id and subscription.tr_key == event.tr_key
            for subscription in self._subscriptions
        ):
            raise KisRealtimeError(
                f"received realtime event for unsubscribed channel: {event.tr_id}/{event.tr_key}"
            )


def _subscription_for(*, channel: str, symbol: str, venue: str) -> RealtimeSubscription:
    normalized_symbol = symbol.strip().upper()
    normalized_venue = venue.strip().upper().replace("-", "_")
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    if channel not in {"trades", "orderbook"}:
        raise ValueError("channel must be one of: trades, orderbook")
    if normalized_venue in {"KRX", "KOSPI", "KOSDAQ"}:
        raise ValueError("KIS SDK only supports overseas realtime data; use Kiwoom for domestic stocks")
    tr_id = lookup(f"overseas.realtime.{channel}").tr_id_for("real")
    tr_key = f"D{normalized_venue}{normalized_symbol}"
    market = normalized_venue
    return RealtimeSubscription(
        channel=channel,
        tr_id=tr_id,
        tr_key=tr_key,
        market=market,
        symbol=normalized_symbol,
    )
