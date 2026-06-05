"""Broker adapter protocols and capability declarations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from modules.domain.market_data import CandleBar


@dataclass(frozen=True, slots=True)
class BrokerCapabilities:
    broker: str
    supports_daily_ohlcv: bool = False
    supports_minute_ohlcv: bool = False
    supports_symbol_master: bool = False
    supports_current_price: bool = False
    supports_realtime: bool = False


class MarketDataAdapter(Protocol):
    capabilities: BrokerCapabilities

    def collect_ohlcv(
        self,
        *,
        symbol: str,
        market: str | None,
        interval: str,
        start: str,
        end: str | None = None,
    ) -> tuple[CandleBar, ...]:
        """Collect canonical OHLCV candles without persisting them."""


class SymbolAdapter(Protocol):
    capabilities: BrokerCapabilities

    def download_symbols(self, *, market: str) -> tuple[object, ...]:
        """Download canonical symbols without persisting them."""

