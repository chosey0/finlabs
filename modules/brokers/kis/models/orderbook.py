from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class OrderBookLevel:
    level: int
    ask_price: Decimal | None
    bid_price: Decimal | None
    ask_volume: int | None
    bid_volume: int | None


@dataclass(frozen=True)
class OrderBookSnapshot:
    market: str
    symbol: str
    tr_id: str
    tr_key: str
    exchange_ts: str
    received_at: str
    received_seq: int
    seq: int
    asks: tuple[OrderBookLevel, ...]
    bids: tuple[OrderBookLevel, ...]
    total_ask_volume: int | None = None
    total_bid_volume: int | None = None
    raw: dict[str, str] = field(default_factory=dict)
