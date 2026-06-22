"""Kiwoom facade implementing the news-intelligence minute-data port."""

from __future__ import annotations

import logging
from datetime import datetime

from modules.brokers.kiwoom.client import KiwoomClient
from modules.brokers.kiwoom.models.ohlcv import ChartBar
from modules.brokers.kiwoom.exceptions import KiwoomError
from modules.domain.news_intelligence import IntelligenceCandle, MarketDataProviderError

from .news_intelligence import normalize_minute_candles

_logger = logging.getLogger(__name__)


class KiwoomMinuteMarketData:
    def __init__(self, client: KiwoomClient) -> None:
        self._client = client

    async def validate_symbol(self, *, market: str, symbol: str) -> None:
        try:
            bars = await self._client.domestic.chart.minute(
                symbol,
                interval_minutes=1,
                max_pages=1,
                market="KRX",
            )
        except KiwoomError as error:
            _logger.warning(
                "Kiwoom validate_symbol failed for %s:%s: %s", market, symbol, error
            )
            raise MarketDataProviderError(
                "Kiwoom market data request failed"
            ) from error
        if not bars:
            raise ValueError(f"Kiwoom did not recognize {market}:{symbol}")

    async def minute_bars(
        self,
        *,
        market: str,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[IntelligenceCandle, ...]:
        try:
            bars: list[ChartBar] = await self._client.domestic.chart.minute(
                symbol,
                interval_minutes=1,
                base_date=window_end.date(),
                market="KRX",
                start_date=window_start.strftime("%Y-%m-%d %H%M%S"),
            )
        except KiwoomError as error:
            _logger.warning(
                "Kiwoom minute_bars failed for %s:%s [%s~%s]: %s",
                market,
                symbol,
                window_start,
                window_end,
                error,
            )
            raise MarketDataProviderError(
                "Kiwoom market data request failed"
            ) from error
        return normalize_minute_candles(
            bars,
            window_start=window_start,
            window_end=window_end,
        )
