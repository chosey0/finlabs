"""Toss market-calendar SDK model → FinLabs canonical model mapping.

Toss responses carry no market code; it is implied by the endpoint, so the
adapter attaches the canonical ``KR``/``US`` market here. A day whose hours are
explicitly null maps to ``closed``; sessions the broker omitted are dropped,
never estimated.
"""

from __future__ import annotations

from datetime import date

from brokers.toss import (
    KrMarketCalendar,
    KrMarketDay,
    MarketSession,
    UsMarketCalendar,
    UsMarketDay,
)
from modules.domain.market_calendar import MarketDay, SessionKind, TradingSession

KR_MARKET = "KR"
US_MARKET = "US"


def kr_calendar_to_market_days(calendar: KrMarketCalendar) -> tuple[MarketDay, ...]:
    return (
        _kr_day(calendar.previous_business_day),
        _kr_day(calendar.today),
        _kr_day(calendar.next_business_day),
    )


def us_calendar_to_market_days(calendar: UsMarketCalendar) -> tuple[MarketDay, ...]:
    return (
        _us_day(calendar.previous_business_day),
        _us_day(calendar.today),
        _us_day(calendar.next_business_day),
    )


def _kr_day(day: KrMarketDay) -> MarketDay:
    sessions: tuple[TradingSession, ...] = ()
    if day.integrated is not None:
        sessions = _sessions(
            ("pre_market", day.integrated.pre_market),
            ("regular", day.integrated.regular_market),
            ("after_market", day.integrated.after_market),
        )
    return _market_day(KR_MARKET, day.date, sessions)


def _us_day(day: UsMarketDay) -> MarketDay:
    sessions = _sessions(
        ("day_market", day.day_market),
        ("pre_market", day.pre_market),
        ("regular", day.regular_market),
        ("after_market", day.after_market),
    )
    return _market_day(US_MARKET, day.date, sessions)


def _market_day(
    market: str, day_date: date, sessions: tuple[TradingSession, ...]
) -> MarketDay:
    return MarketDay(
        market=market,
        date=day_date,
        status="open" if sessions else "closed",
        sessions=sessions,
    )


def _sessions(
    *pairs: tuple[SessionKind, MarketSession | None],
) -> tuple[TradingSession, ...]:
    converted = [
        TradingSession(
            kind=kind,
            start_at=session.start_time,
            end_at=session.end_time,
            auction_start_at=session.single_price_auction_start_time,
            auction_end_at=session.single_price_auction_end_time,
        )
        for kind, session in pairs
        if session is not None
    ]
    return tuple(sorted(converted, key=lambda session: session.start_at))
