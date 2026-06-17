from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from modules.brokers.kis.endpoints.registry import lookup
from modules.brokers.kis.exceptions import KisRealtimeError
from modules.brokers.kis.models.orderbook import OrderBookSnapshot
from modules.brokers.kis.models.tick import RealtimeTick
from modules.brokers.kis.overseas.exchange import normalize_overseas_exchange
from modules.brokers.kis.types import Environment

Feed = Literal["delayed", "realtime"]

DOMESTIC_VENUES = frozenset({"KRX", "KOSPI", "KOSDAQ"})

_FEED_PREFIXES: dict[Feed, str] = {"delayed": "D", "realtime": "R"}


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


def subscription_for(
    *,
    channel: str,
    symbol: str,
    venue: str,
    feed: Feed | None = None,
    environment: Environment = "real",
) -> RealtimeSubscription:
    """Build a RealtimeSubscription for a domestic or overseas venue.

    Domestic venues (KRX/KOSPI/KOSDAQ) subscribe with the bare 6-digit code
    and are always realtime. Overseas venues prefix the tr_key with the feed
    selector: "D" (delayed, default) or "R" (realtime — requires a paid
    realtime subscription on the KIS account).
    """
    normalized_symbol = symbol.strip().upper()
    normalized_venue = venue.strip().upper().replace("-", "_")
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    if channel not in {"trades", "orderbook"}:
        raise ValueError("channel must be one of: trades, orderbook")
    if normalized_venue in DOMESTIC_VENUES:
        if feed == "delayed":
            raise ValueError(
                "domestic realtime data has no delayed feed; omit the feed option"
            )
        tr_id = lookup(f"domestic.realtime.{channel}").tr_id_for(environment)
        tr_key = normalized_symbol
    else:
        normalized_venue = normalize_overseas_exchange(normalized_venue)
        selected_feed: Feed = feed or "delayed"
        if selected_feed not in _FEED_PREFIXES:
            raise ValueError("feed must be one of: delayed, realtime")
        tr_id = lookup(f"overseas.realtime.{channel}").tr_id_for(environment)
        tr_key = f"{_FEED_PREFIXES[selected_feed]}{normalized_venue}{normalized_symbol}"
    return RealtimeSubscription(
        channel=channel,
        tr_id=tr_id,
        tr_key=tr_key,
        market=normalized_venue,
        symbol=normalized_symbol,
    )
