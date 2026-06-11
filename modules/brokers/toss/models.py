from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from modules.brokers.toss.types import Currency


@dataclass(frozen=True)
class CurrentPrice:
    symbol: str
    timestamp: datetime | None
    last_price: Decimal
    currency: Currency
    raw: dict[str, Any]


@dataclass(frozen=True)
class Candle:
    symbol: str
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: Decimal
    currency: Currency
    raw: dict[str, Any]


@dataclass(frozen=True)
class CandlePage:
    candles: tuple[Candle, ...]
    next_before: datetime | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class KoreanMarketDetail:
    liquidation_trading: bool
    nxt_supported: bool
    krx_trading_suspended: bool
    nxt_trading_suspended: bool | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str
    english_name: str
    isin_code: str
    market: str
    security_type: str
    is_common_share: bool
    status: str
    currency: Currency
    list_date: date | None
    delist_date: date | None
    shares_outstanding: Decimal
    leverage_factor: Decimal | None
    korean_market_detail: KoreanMarketDetail | None
    raw: dict[str, Any]
