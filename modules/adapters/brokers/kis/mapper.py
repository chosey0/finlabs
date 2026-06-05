"""KIS SDK model → FinLabs canonical model mapping."""

from __future__ import annotations

from modules.brokers.kis import OhlcvBar, OverseasMinuteBar
from modules.domain.market_data import CandleBar


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

