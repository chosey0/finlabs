"""Translate Kiwoom minute chart rows into aware canonical candles."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from modules.brokers.kiwoom.models.ohlcv import ChartBar
from modules.domain.news_intelligence import KST, IntelligenceCandle

_KIWOOM_MINUTE_FORMAT = "%Y-%m-%d %H:%M:%S"


def normalize_minute_candles(
    bars: list[ChartBar] | tuple[ChartBar, ...],
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[IntelligenceCandle, ...]:
    """Normalize, range-check, deduplicate and order Kiwoom one-minute bars."""

    _require_aware(window_start, "window_start")
    _require_aware(window_end, "window_end")
    if window_end < window_start:
        raise ValueError("window_end must be on or after window_start")

    selected: dict[datetime, IntelligenceCandle] = {}
    expected_identity: tuple[str, str, str] | None = None
    for bar in bars:
        if bar.interval != "1min":
            raise ValueError("only Kiwoom one-minute bars are supported")
        timestamp = datetime.strptime(bar.timestamp, _KIWOOM_MINUTE_FORMAT).replace(
            tzinfo=KST
        )
        if not window_start <= timestamp <= window_end:
            raise ValueError("Kiwoom candle fell outside the requested range")
        identity = (bar.market, bar.symbol, bar.interval)
        if expected_identity is None:
            expected_identity = identity
        elif identity != expected_identity:
            raise ValueError("Kiwoom candle identity changed within one response")

        candidate = IntelligenceCandle(
            market=bar.market,
            symbol=bar.symbol,
            interval=bar.interval,
            timestamp=timestamp,
            open=Decimal(bar.open),
            high=Decimal(bar.high),
            low=Decimal(bar.low),
            close=Decimal(bar.close),
            volume=bar.volume,
        )
        existing = selected.get(timestamp)
        if existing is not None and existing != candidate:
            raise ValueError("conflicting duplicate Kiwoom candle")
        selected[timestamp] = candidate

    return tuple(selected[timestamp] for timestamp in sorted(selected))


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
