"""Canonical contracts for market surge-event extraction."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

TurnoverSource = Literal["reported", "estimated_close_x_volume"]


@dataclass(frozen=True, slots=True)
class DailyPriceBar:
    """Broker-neutral daily price inputs required for surge detection."""

    market: str
    ticker: str
    trade_date: date
    close: Decimal
    volume: Decimal
    turnover: Decimal
    turnover_source: TurnoverSource
    price_source: str

    def __post_init__(self) -> None:
        if not self.market.strip():
            raise ValueError("market must not be empty")
        if not self.ticker.strip():
            raise ValueError("ticker must not be empty")
        if self.close <= 0:
            raise ValueError("close must be positive")
        if self.volume < 0:
            raise ValueError("volume must not be negative")
        if self.turnover < 0:
            raise ValueError("turnover must not be negative")
        if not self.price_source.strip():
            raise ValueError("price_source must not be empty")


@dataclass(frozen=True, slots=True)
class SurgeEvent:
    """A market session that satisfies the configured surge conditions."""

    market: str
    ticker: str
    surge_date: date
    close: Decimal
    turnover: Decimal
    turnover_source: TurnoverSource
    return_1d: Decimal
    max_return_3d: Decimal
    trigger_sessions: int
    price_source: str

    def __post_init__(self) -> None:
        if self.trigger_sessions not in (1, 2, 3):
            raise ValueError("trigger_sessions must be 1, 2, or 3")
