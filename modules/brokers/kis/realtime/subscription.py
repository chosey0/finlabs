from __future__ import annotations

from dataclasses import dataclass

from modules.brokers.kis.endpoints.registry import lookup
from modules.brokers.kis.exceptions import KisRealtimeError
from modules.brokers.kis.models.orderbook import OrderBookSnapshot
from modules.brokers.kis.models.tick import RealtimeTick


@dataclass(frozen=True)
class RealtimeSubscription:
    channel: str
    tr_id: str
    tr_key: str
    market: str
    symbol: str


class SubscriptionRegistry:
    """Track realtime subscriptions and validate incoming events."""

    def __init__(self) -> None:
        self._subscriptions: set[RealtimeSubscription] = set()

    @property
    def subscriptions(self) -> frozenset[RealtimeSubscription]:
        return frozenset(self._subscriptions)

    def add(self, subscription: RealtimeSubscription) -> None:
        self._subscriptions.add(subscription)

    def discard(self, subscription: RealtimeSubscription) -> None:
        self._subscriptions.discard(subscription)

    def all(self) -> tuple[RealtimeSubscription, ...]:
        return tuple(self._subscriptions)

    def validate_event(self, event: RealtimeTick | OrderBookSnapshot) -> None:
        if not any(
            subscription.tr_id == event.tr_id and subscription.tr_key == event.tr_key
            for subscription in self._subscriptions
        ):
            raise KisRealtimeError(
                f"received realtime event for unsubscribed channel: {event.tr_id}/{event.tr_key}"
            )


def subscription_for(*, channel: str, symbol: str, venue: str) -> RealtimeSubscription:
    normalized_symbol = symbol.strip().upper()
    normalized_venue = venue.strip().upper().replace("-", "_")
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    if channel not in {"trades", "orderbook"}:
        raise ValueError("channel must be one of: trades, orderbook")
    if normalized_venue in {"KRX", "KOSPI", "KOSDAQ"}:
        raise ValueError(
            "KIS SDK only supports overseas realtime data; use Kiwoom for domestic stocks"
        )
    tr_id = lookup(f"overseas.realtime.{channel}").tr_id_for("real")
    tr_key = f"D{normalized_venue}{normalized_symbol}"
    return RealtimeSubscription(
        channel=channel,
        tr_id=tr_id,
        tr_key=tr_key,
        market=normalized_venue,
        symbol=normalized_symbol,
    )
