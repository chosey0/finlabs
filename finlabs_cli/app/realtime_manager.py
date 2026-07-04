from __future__ import annotations

from typing import Any

from brokers.kis import KisRealtimeError

from finlabs_cli.app.broker_registry import build_client
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.models.account import Account
from finlabs_cli.models.realtime import ActiveSubscription, RealtimeSubscriptionStatus


class RealtimeManager:
    def __init__(self, account: Account, token_store: JsonTokenStore) -> None:
        self.account = account
        self.token_store = token_store
        self._client: Any | None = None
        self._session: Any | None = None
        self._subscriptions: list[tuple[ActiveSubscription, Any]] = []
        self._statuses: dict[ActiveSubscription, RealtimeSubscriptionStatus] = {}

    async def __aenter__(self) -> "RealtimeManager":
        self._client = build_client(self.account, self.token_store)
        await self._client.__aenter__()
        self._session = self._client.realtime.session()
        await self._session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is not None:
            await self._session.__aexit__(exc_type, exc, tb)
            self._session = None
        if self._client is not None:
            await self._client.__aexit__(exc_type, exc, tb)
            self._client = None

    def subscriptions(self) -> list[ActiveSubscription]:
        return [item for item, _sdk_subscription in self._subscriptions]

    def subscription_statuses(self) -> list[RealtimeSubscriptionStatus]:
        return [
            self._statuses[item]
            for item, _sdk_subscription in self._subscriptions
            if item in self._statuses
        ]

    async def subscribe(
        self,
        *,
        channel: str,
        symbol: str,
        venue: str = "",
        feed: str | None = None,
    ) -> None:
        if self._session is None:
            raise RuntimeError("RealtimeManager is not connected")
        if channel == "trades":
            sdk_subscription = await self._subscribe_trades(
                symbol=symbol,
                venue=venue,
                feed=feed,
            )
        elif channel == "orderbook":
            sdk_subscription = await self._subscribe_orderbook(
                symbol=symbol,
                venue=venue,
                feed=feed,
            )
        else:
            raise ValueError("channel must be one of: trades, orderbook")
        active = ActiveSubscription(
            account_alias=self.account.alias,
            broker=self.account.broker,
            channel=channel,
            market=getattr(sdk_subscription, "market", venue or "KRX"),
            symbol=symbol.strip().upper(),
            tr_id=getattr(sdk_subscription, "tr_id", ""),
            tr_key=getattr(sdk_subscription, "tr_key", ""),
        )
        self._subscriptions.append((active, sdk_subscription))
        self._statuses[active] = RealtimeSubscriptionStatus(subscription=active)

    async def unsubscribe(self, subscription: ActiveSubscription) -> None:
        if self._session is None:
            raise RuntimeError("RealtimeManager is not connected")
        for active, sdk_subscription in list(self._subscriptions):
            if active == subscription:
                try:
                    await self._session.unsubscribe(sdk_subscription)
                except KisRealtimeError as exc:
                    if "not found" not in str(exc).lower():
                        raise
                self._subscriptions.remove((active, sdk_subscription))
                self._statuses.pop(active, None)
                return

    async def unsubscribe_all(self) -> None:
        for subscription in list(self.subscriptions()):
            await self.unsubscribe(subscription)

    async def stream(self):
        if self._session is None:
            raise RuntimeError("RealtimeManager is not connected")
        async for event in self._session.stream():
            yield event

    def record_event(self, event: Any) -> None:
        tr_id = str(getattr(event, "tr_id", ""))
        tr_key = str(getattr(event, "tr_key", ""))
        exchange_ts = str(getattr(event, "exchange_ts", "")) or "-"
        for active, _sdk_subscription in self._subscriptions:
            if active.tr_id == tr_id and active.tr_key == tr_key:
                status = self._statuses[active]
                status.exchange_ts = exchange_ts
                status.received += 1
                return

    async def _subscribe_trades(self, *, symbol: str, venue: str, feed: str | None):
        if self.account.broker == "kis":
            return await self._session.subscribe_trades(
                symbol,
                venue,
                feed=feed,
            )
        return await self._session.subscribe_trades(symbol)

    async def _subscribe_orderbook(self, *, symbol: str, venue: str, feed: str | None):
        if self.account.broker == "kis":
            return await self._session.subscribe_orderbook(
                symbol,
                venue,
                feed=feed,
            )
        return await self._session.subscribe_orderbook(symbol)
