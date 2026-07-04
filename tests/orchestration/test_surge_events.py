"""Historical market surge extraction and persistence tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import duckdb
import pytest

from modules.adapters.brokers.kis.mapper import ohlcv_to_daily_price_bar
from modules.adapters.brokers.toss.market_data import candle_to_daily_price_bar
from brokers.kis.models.ohlcv import OhlcvBar
from brokers.toss.models import Candle
from modules.domain.surge import DailyPriceBar
from modules.orchestration.surge_events import (
    extract_and_store_surge_events,
    extract_surge_events,
)


def _bar(
    trade_date: str,
    close: str,
    turnover: str,
    *,
    ticker: str = "005930",
) -> DailyPriceBar:
    return DailyPriceBar(
        market="KOSPI",
        ticker=ticker,
        trade_date=datetime.strptime(trade_date, "%Y-%m-%d").date(),
        close=Decimal(close),
        volume=Decimal("1000000"),
        turnover=Decimal(turnover),
        turnover_source="reported",
        price_source="fixture",
    )


def test_kis_adapter_prefers_reported_turnover() -> None:
    bar = ohlcv_to_daily_price_bar(
        OhlcvBar(
            market="KOSPI",
            symbol="005930",
            interval="1d",
            timestamp="20260612",
            open=Decimal("100"),
            high=Decimal("112"),
            low=Decimal("99"),
            close=Decimal("111"),
            volume=100,
            amount=Decimal("12000000000"),
        )
    )

    assert bar.turnover == Decimal("12000000000")
    assert bar.turnover_source == "reported"
    assert bar.trade_date.isoformat() == "2026-06-12"


def test_toss_adapter_marks_close_times_volume_as_estimate() -> None:
    bar = candle_to_daily_price_bar(
        Candle(
            symbol="005930",
            timestamp=datetime(2026, 6, 12, tzinfo=timezone.utc),
            open_price=Decimal("100"),
            high_price=Decimal("112"),
            low_price=Decimal("99"),
            close_price=Decimal("111"),
            volume=Decimal("100000000"),
            currency="KRW",
            raw={},
        ),
        market="KOSPI",
    )

    assert bar.turnover == Decimal("11100000000")
    assert bar.turnover_source == "estimated_close_x_volume"
    assert bar.price_source == "toss"


def test_extracts_one_day_surge_with_turnover_threshold() -> None:
    events = extract_surge_events(
        [
            _bar("2026-06-10", "100", "9000000000"),
            _bar("2026-06-11", "110", "10000000000"),
        ]
    )

    assert len(events) == 1
    assert events[0].surge_date.isoformat() == "2026-06-11"
    assert events[0].return_1d == Decimal("0.1")
    assert events[0].trigger_sessions == 1


def test_extracts_three_session_surge_across_weekend() -> None:
    events = extract_surge_events(
        [
            _bar("2026-06-04", "100", "1000000000"),
            _bar("2026-06-05", "103", "1000000000"),
            _bar("2026-06-08", "106", "1000000000"),
            _bar("2026-06-09", "111", "15000000000"),
        ]
    )

    assert len(events) == 1
    assert events[0].surge_date.isoformat() == "2026-06-09"
    assert events[0].return_1d < Decimal("0.10")
    assert events[0].max_return_3d == Decimal("0.11")
    assert events[0].trigger_sessions == 3


def test_rejects_low_turnover_and_duplicate_dates() -> None:
    low_turnover = [
        _bar("2026-06-10", "100", "1000000000"),
        _bar("2026-06-11", "120", "9999999999"),
    ]
    assert extract_surge_events(low_turnover) == ()

    with pytest.raises(ValueError, match="duplicate daily bar"):
        extract_surge_events([low_turnover[0], low_turnover[0]])


def test_extract_and_store_is_idempotent() -> None:
    connection = duckdb.connect(":memory:")
    bars = [
        _bar("2026-06-10", "100", "1000000000"),
        _bar("2026-06-11", "111", "12000000000"),
    ]

    first = extract_and_store_surge_events(connection, bars)
    second = extract_and_store_surge_events(connection, bars)

    assert first == second
    assert connection.execute(
        """
        SELECT market, ticker, surge_date, trigger_sessions
        FROM surge_events
        """
    ).fetchall() == [("KOSPI", "005930", datetime(2026, 6, 11).date(), 1)]
