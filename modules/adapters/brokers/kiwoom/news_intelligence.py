"""Translate Kiwoom chart rows into aware canonical candles.

Supports one-minute and N-minute bars (``ka10080``; ``1min``..``60min``) and
daily bars (``ka10081``; ``1d``). Minute bars carry a full ``cntr_tm`` datetime;
daily bars carry only a ``dt`` date, so a daily candle is anchored at the KST
regular-session close (15:30) — that way clicking a daily candle still yields a
meaningful one-hour news window (the last hour before the close).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from brokers.kiwoom.models.ohlcv import ChartBar
from modules.domain.news_intelligence import KST, IntelligenceCandle

_KIWOOM_MINUTE_FORMAT = "%Y-%m-%d %H:%M:%S"
_KIWOOM_DAILY_FORMAT = "%Y-%m-%d"
_MINUTE_INTERVALS = frozenset(
    {"1min", "3min", "5min", "10min", "15min", "30min", "45min", "60min"}
)
_DAILY_INTERVAL = "1d"
# KST regular-session close for KOSPI/KOSDAQ; daily candles anchor here.
_DAILY_CLOSE_HOUR = 15
_DAILY_CLOSE_MINUTE = 30


def normalize_chart_candles(
    bars: list[ChartBar] | tuple[ChartBar, ...],
    *,
    window_start: datetime,
    window_end: datetime,
) -> tuple[IntelligenceCandle, ...]:
    """Normalize, range-check, deduplicate and order Kiwoom chart bars.

    Accepts every minute interval and the daily interval; mixing intervals in a
    single response is rejected.
    """

    _require_aware(window_start, "window_start")
    _require_aware(window_end, "window_end")
    if window_end < window_start:
        raise ValueError("window_end must be on or after window_start")

    selected: dict[datetime, IntelligenceCandle] = {}
    expected_identity: tuple[str, str, str] | None = None
    for bar in bars:
        timestamp = _bar_timestamp(bar)
        if not _within_window(bar, timestamp, window_start, window_end):
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
            # Kiwoom reports 거래대금 (traded value) as ``amount``; fall back to
            # close × volume when a bar omits it, matching the reaction adapter.
            turnover=bar.amount
            if bar.amount is not None
            else bar.close * bar.volume,
        )
        existing = selected.get(timestamp)
        if existing is not None and existing != candidate:
            raise ValueError("conflicting duplicate Kiwoom candle")
        selected[timestamp] = candidate

    return tuple(selected[timestamp] for timestamp in sorted(selected))


def _bar_timestamp(bar: ChartBar) -> datetime:
    if bar.interval in _MINUTE_INTERVALS:
        return datetime.strptime(bar.timestamp, _KIWOOM_MINUTE_FORMAT).replace(
            tzinfo=KST
        )
    if bar.interval == _DAILY_INTERVAL:
        day = datetime.strptime(bar.timestamp, _KIWOOM_DAILY_FORMAT).date()
        return datetime(
            day.year,
            day.month,
            day.day,
            _DAILY_CLOSE_HOUR,
            _DAILY_CLOSE_MINUTE,
            tzinfo=KST,
        )
    raise ValueError(f"unsupported Kiwoom chart interval: {bar.interval}")


def _within_window(
    bar: ChartBar,
    timestamp: datetime,
    window_start: datetime,
    window_end: datetime,
) -> bool:
    if bar.interval == _DAILY_INTERVAL:
        # Daily bars are compared by calendar date so a date-spanning request
        # includes its boundary days regardless of the intraday close anchor.
        return window_start.date() <= timestamp.date() <= window_end.date()
    return window_start <= timestamp <= window_end


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
