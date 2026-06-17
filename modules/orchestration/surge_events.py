"""Broker-neutral use case for extracting historical market surge events."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date
from decimal import Decimal

import duckdb

from modules.domain.surge import DailyPriceBar, SurgeEvent
from modules.storage.surge_events import upsert_surge_events

DEFAULT_MIN_TURNOVER = Decimal("10000000000")
DEFAULT_RETURN_THRESHOLD = Decimal("0.10")


def extract_surge_events(
    bars: Iterable[DailyPriceBar],
    *,
    min_turnover: Decimal = DEFAULT_MIN_TURNOVER,
    return_threshold: Decimal = DEFAULT_RETURN_THRESHOLD,
) -> tuple[SurgeEvent, ...]:
    """Extract sessions meeting turnover and one-to-three-session return rules."""

    if min_turnover < 0:
        raise ValueError("min_turnover must not be negative")
    if return_threshold <= 0:
        raise ValueError("return_threshold must be positive")

    grouped: dict[tuple[str, str], list[DailyPriceBar]] = defaultdict(list)
    for bar in bars:
        grouped[(bar.market, bar.ticker)].append(bar)

    events: list[SurgeEvent] = []
    for series in grouped.values():
        ordered = sorted(series, key=lambda bar: bar.trade_date)
        _reject_duplicate_dates(ordered)
        for index, current in enumerate(ordered):
            if index == 0 or current.turnover < min_turnover:
                continue
            returns = tuple(
                (
                    sessions,
                    _return_rate(current.close, ordered[index - sessions].close),
                )
                for sessions in range(1, min(3, index) + 1)
            )
            qualifying = tuple(item for item in returns if item[1] >= return_threshold)
            if not qualifying:
                continue
            events.append(
                SurgeEvent(
                    market=current.market,
                    ticker=current.ticker,
                    surge_date=current.trade_date,
                    close=current.close,
                    turnover=current.turnover,
                    turnover_source=current.turnover_source,
                    return_1d=returns[0][1],
                    max_return_3d=max(rate for _, rate in returns),
                    trigger_sessions=min(sessions for sessions, _ in qualifying),
                    price_source=current.price_source,
                )
            )
    return tuple(
        sorted(events, key=lambda event: (event.surge_date, event.market, event.ticker))
    )


def extract_and_store_surge_events(
    connection: duckdb.DuckDBPyConnection,
    bars: Iterable[DailyPriceBar],
    *,
    min_turnover: Decimal = DEFAULT_MIN_TURNOVER,
    return_threshold: Decimal = DEFAULT_RETURN_THRESHOLD,
) -> tuple[SurgeEvent, ...]:
    """Extract events and persist them through the storage layer."""

    events = extract_surge_events(
        bars,
        min_turnover=min_turnover,
        return_threshold=return_threshold,
    )
    upsert_surge_events(connection, events)
    return events


def _return_rate(current_close: Decimal, previous_close: Decimal) -> Decimal:
    return current_close / previous_close - Decimal(1)


def _reject_duplicate_dates(bars: list[DailyPriceBar]) -> None:
    seen: set[date] = set()
    for bar in bars:
        if bar.trade_date in seen:
            raise ValueError(
                f"duplicate daily bar for {bar.market}/{bar.ticker}/{bar.trade_date.isoformat()}"
            )
        seen.add(bar.trade_date)
