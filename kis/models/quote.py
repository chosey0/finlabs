from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class CurrentPrice:
    """Normalized snapshot of one symbol's current price.

    Fields are intentionally generic for overseas markets. `raw` preserves
    the original KIS payload
    for debugging or downstream re-parsing.
    """

    market: str
    symbol: str
    name: str
    price: Decimal | None
    currency: str
    change: Decimal | None
    change_rate: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    volume: int | None
    raw: dict[str, Any] = field(default_factory=dict)
