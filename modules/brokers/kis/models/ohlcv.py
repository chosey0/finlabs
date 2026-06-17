from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class OhlcvBar:
    """One OHLCV row for daily / weekly / monthly / yearly intervals.

    Used by overseas chart endpoints. The `interval` field follows FinLabs'
    canonical labels: ``1d`` / ``1w`` / ``1mo`` / ``1y``.
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
    change: Decimal | None = None
    change_rate: Decimal | None = None
    amount: Decimal | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomesticMinuteBar:
    """One minute bar for a domestic stock trading session.

    ``cumulative_amount`` is the session-to-date transaction amount reported
    by KIS at this bar's timestamp, not the transaction amount of this minute.
    """

    market: str
    symbol: str
    business_date: str
    time: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    cumulative_amount: Decimal
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OverseasMinuteBar:
    """One minute bar for overseas stocks.

    KIS reports both the exchange's local clock and the Korean clock; both
    are preserved as strings so the original payload semantics are not lost
    in timezone conversion.
    """

    market: str
    symbol: str
    interval_minutes: int
    local_business_date: str
    local_date: str
    local_time: str
    korea_date: str
    korea_time: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    amount: Decimal
    raw: dict[str, Any] = field(default_factory=dict)
