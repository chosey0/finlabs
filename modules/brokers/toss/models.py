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
class MarketSession:
    start_time: datetime
    end_time: datetime
    single_price_auction_start_time: datetime | None
    single_price_auction_end_time: datetime | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class KrMarketHours:
    pre_market: MarketSession | None
    regular_market: MarketSession | None
    after_market: MarketSession | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class KrMarketDay:
    date: date
    integrated: KrMarketHours | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class KrMarketCalendar:
    today: KrMarketDay
    previous_business_day: KrMarketDay
    next_business_day: KrMarketDay
    raw: dict[str, Any]


@dataclass(frozen=True)
class UsMarketDay:
    date: date
    day_market: MarketSession | None
    pre_market: MarketSession | None
    regular_market: MarketSession | None
    after_market: MarketSession | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class UsMarketCalendar:
    today: UsMarketDay
    previous_business_day: UsMarketDay
    next_business_day: UsMarketDay
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
