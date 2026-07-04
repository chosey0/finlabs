"""Toss market-data models to canonical FinLabs market inputs."""

from __future__ import annotations

from decimal import Decimal

from brokers.toss import Candle
from modules.domain.surge import DailyPriceBar


def candle_to_daily_price_bar(candle: Candle, *, market: str) -> DailyPriceBar:
    """Map a Toss candle, estimating turnover because the API omits it."""

    normalized_market = market.strip().upper()
    if not normalized_market:
        raise ValueError("market must not be empty")
    close = Decimal(candle.close_price)
    volume = Decimal(candle.volume)
    return DailyPriceBar(
        market=normalized_market,
        ticker=candle.symbol.strip().upper(),
        trade_date=candle.timestamp.date(),
        close=close,
        volume=volume,
        turnover=close * volume,
        turnover_source="estimated_close_x_volume",
        price_source="toss",
    )
