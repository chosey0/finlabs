"""Canonical market-calendar contracts shared across FinLabs layers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

SessionKind = Literal["pre_market", "regular", "after_market", "day_market"]
DayStatus = Literal["open", "closed", "unknown"]


@dataclass(frozen=True, slots=True)
class TradingSession:
    """Broker-agnostic trading session within a single market day."""

    kind: SessionKind
    start_at: datetime
    end_at: datetime
    auction_start_at: datetime | None = None
    auction_end_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MarketDay:
    """Operating status and sessions of one market on one calendar date.

    ``status`` is ``open`` when the source reported at least one session,
    ``closed`` when it explicitly reported a day without sessions, and
    ``unknown`` when no source could resolve the day.
    """

    market: str
    date: date
    status: DayStatus
    sessions: tuple[TradingSession, ...]
