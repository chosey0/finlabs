from __future__ import annotations

from typing import Any

from finlabs_cli.app.broker_registry import build_client
from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.models.account import Account
from finlabs_cli.models.realtime import ActiveSubscription


class RealtimeManager:
    def __init__(self, account: Account, token_store: JsonTokenStore) -> None:
        self.account = account
        self.token_store = token_store
        self._client: Any | None = None
        self._session: Any | None = None
        self._subscriptions: list[tuple[ActiveSubscription, Any]] = []

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

    async def subscribe(self, *, channel: str, symbol: str, venue: str = "") -> None:
        if self._session is None:
            raise RuntimeError("RealtimeManager is not connected")
        if channel == "trades":
            sdk_subscription = await self._subscribe_trades(symbol=symbol, venue=venue)
        elif channel == "orderbook":
            sdk_subscription = await self._subscribe_orderbook(symbol=symbol, venue=venue)
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

    async def unsubscribe(self, subscription: ActiveSubscription) -> None:
        if self._session is None:
            raise RuntimeError("RealtimeManager is not connected")
        for active, sdk_subscription in list(self._subscriptions):
            if active == subscription:
                await self._session.unsubscribe(sdk_subscription)
                self._subscriptions.remove((active, sdk_subscription))
                return

    async def unsubscribe_all(self) -> None:
        for subscription in list(self.subscriptions()):
            await self.unsubscribe(subscription)

    async def stream(self):
        if self._session is None:
            raise RuntimeError("RealtimeManager is not connected")
        async for event in self._session.stream():
            yield event

    async def _subscribe_trades(self, *, symbol: str, venue: str):
        if self.account.broker == "kis":
            return await self._session.subscribe_trades(
                symbol,
                venue,
                feed="realtime" if venue.strip().upper() not in {"KRX", "KOSPI", "KOSDAQ"} else None,
            )
        return await self._session.subscribe_trades(symbol)

    async def _subscribe_orderbook(self, *, symbol: str, venue: str):
        if self.account.broker == "kis":
            return await self._session.subscribe_orderbook(
                symbol,
                venue,
                feed="realtime" if venue.strip().upper() not in {"KRX", "KOSPI", "KOSDAQ"} else None,
            )
        return await self._session.subscribe_orderbook(symbol)
