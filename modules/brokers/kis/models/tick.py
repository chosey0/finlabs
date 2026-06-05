from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class RealtimeTick:
    market: str
    symbol: str
    tr_id: str
    tr_key: str
    exchange_ts: str
    received_at: str
    received_seq: int
    seq: int
    price: Decimal | None
    volume: int | None
    total_volume: int | None = None
    amount: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    raw: dict[str, str] = field(default_factory=dict)
