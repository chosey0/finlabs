from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActiveSubscription:
    account_alias: str
    broker: str
    channel: str
    market: str
    symbol: str
    tr_id: str
    tr_key: str


@dataclass
class RealtimeSubscriptionStatus:
    subscription: ActiveSubscription
    exchange_ts: str = "-"
    received: int = 0
