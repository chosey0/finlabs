from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ChartBar:
    """One Kiwoom domestic chart row.

    ``interval`` uses SDK labels such as ``1tick``, ``1min``, ``1d``, ``1w``,
    ``1mo``, and ``1y``. Kiwoom encodes price direction as a leading sign on
    some price fields, so parsed OHLC prices are normalized to absolute values
    while ``change`` preserves its sign.
    """

    market: str
    symbol: str
    interval: str
    timestamp: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Decimal | None = None
    change: Decimal | None = None
    change_signal: str | None = None
    turnover_rate: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)
