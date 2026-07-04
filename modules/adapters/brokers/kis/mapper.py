"""KIS SDK model → FinLabs canonical model mapping."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from brokers.kis import OhlcvBar, OverseasMinuteBar
from modules.domain.market_data import CandleBar
from modules.domain.surge import DailyPriceBar


def ohlcv_to_candle(bar: OhlcvBar) -> CandleBar:
    return CandleBar(
        market=bar.market,
        symbol=bar.symbol,
        interval=bar.interval,
        timestamp=bar.timestamp,
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=int(bar.volume),
    )


def minute_to_candle(bar: OverseasMinuteBar) -> CandleBar:
    return CandleBar(
        market=bar.market,
        symbol=bar.symbol,
        interval=f"{bar.interval_minutes}m",
        timestamp=f"{bar.local_date} {bar.local_time}",
        open=float(bar.open),
        high=float(bar.high),
        low=float(bar.low),
        close=float(bar.close),
        volume=int(bar.volume),
    )


def ohlcv_to_daily_price_bar(bar: OhlcvBar) -> DailyPriceBar:
    """Map a KIS daily bar into the surge detector's canonical input."""

    close = Decimal(bar.close)
    volume = Decimal(bar.volume)
    return DailyPriceBar(
        market=bar.market.strip().upper(),
        ticker=bar.symbol.strip().upper(),
        trade_date=_parse_trade_date(bar.timestamp),
        close=close,
        volume=volume,
        turnover=Decimal(bar.amount) if bar.amount is not None else close * volume,
        turnover_source=(
            "reported" if bar.amount is not None else "estimated_close_x_volume"
        ),
        price_source="kis",
    )


def _parse_trade_date(value: str) -> date:
    normalized = value.strip()
    if len(normalized) == 8 and normalized.isdigit():
        return datetime.strptime(normalized, "%Y%m%d").date()
    return date.fromisoformat(normalized[:10])
