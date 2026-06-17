from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from modules.brokers.kis.exceptions import KisRealtimeError
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
        self._pending_control: dict[
            tuple[str, str], asyncio.Future[None]
        ] = {}
        self._active_streams = 0

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
        self._active_streams += 1
        try:
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
                if frame.lstrip().startswith("{"):
                    self._handle_control_frame(frame)
                    continue
                for event in self._frame_processor.process(frame):
                    yield event
        finally:
            self._active_streams -= 1

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
        wait_control: bool = True,
    ) -> None:
        if self._connection is None:
            raise RuntimeError("RealtimeSession must be used as an async context manager")
        pending = self._create_pending_control(subscription)
        try:
            await self._connection.send_subscription(subscription, tr_type=tr_type)
            if wait_control and self._active_streams:
                await self._wait_pending_control(subscription, pending)
            else:
                self._discard_pending_control(subscription, pending)
        except Exception:
            self._discard_pending_control(subscription, pending)
            raise

    async def _resubscribe(self) -> None:
        for subscription in self._registry.all():
            await self._send_subscription(
                subscription,
                tr_type="1",
                wait_control=False,
            )

    def _create_pending_control(
        self, subscription: RealtimeSubscription
    ) -> asyncio.Future[None]:
        loop = asyncio.get_running_loop()
        pending: asyncio.Future[None] = loop.create_future()
        self._pending_control[(subscription.tr_id, subscription.tr_key)] = pending
        return pending

    async def _wait_pending_control(
        self,
        subscription: RealtimeSubscription,
        pending: asyncio.Future[None],
    ) -> None:
        try:
            await asyncio.wait_for(pending, timeout=5.0)
        except TimeoutError as exc:
            raise KisRealtimeError(
                "timed out waiting for realtime subscription response"
            ) from exc
        finally:
            self._discard_pending_control(subscription, pending)

    def _discard_pending_control(
        self,
        subscription: RealtimeSubscription,
        pending: asyncio.Future[None],
    ) -> None:
        key = (subscription.tr_id, subscription.tr_key)
        if self._pending_control.get(key) is pending:
            self._pending_control.pop(key, None)

    def _handle_control_frame(self, frame: str) -> None:
        try:
            payload = json.loads(frame)
        except json.JSONDecodeError:
            logger.warning("ignored malformed realtime JSON frame")
            return
        header = payload.get("header")
        body = payload.get("body")
        if not isinstance(header, dict) or not isinstance(body, dict):
            logger.warning("ignored malformed realtime control frame")
            return
        tr_id = str(header.get("tr_id") or "")
        tr_key = str(header.get("tr_key") or "")
        msg = str(body.get("msg1") or "")
        rt_cd = str(body.get("rt_cd") or "")
        pending = self._pending_control.get((tr_id, tr_key))
        if _is_control_success(msg=msg, rt_cd=rt_cd):
            if pending is not None and not pending.done():
                pending.set_result(None)
            return
        if msg:
            logger.warning("realtime websocket control message: %s", msg)
        error = KisRealtimeError(msg or "realtime websocket control message failed")
        if pending is not None and not pending.done():
            pending.set_exception(error)


def _is_control_success(*, msg: str, rt_cd: str) -> bool:
    if rt_cd and rt_cd != "0":
        return False
    return not msg or "SUCCESS" in msg
