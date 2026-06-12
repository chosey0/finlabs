from __future__ import annotations

import re
from datetime import date, datetime
from typing import TYPE_CHECKING, Iterable

from modules.brokers.toss.models import (
    CandlePage,
    CurrentPrice,
    KrMarketCalendar,
    UsMarketCalendar,
)
from modules.brokers.toss.parsers import (
    parse_candle_page,
    parse_current_price,
    parse_kr_market_calendar,
    parse_us_market_calendar,
    result_list,
)
from modules.brokers.toss.types import CandleInterval

if TYPE_CHECKING:
    from modules.brokers.toss.client import TossClient

_SYMBOL_PATTERN = re.compile(r"^[A-Za-z0-9.\-]+$")


class MarketDataAPI:
    def __init__(self, parent: "TossClient") -> None:
        self._parent = parent

    async def prices(self, symbols: str | Iterable[str]) -> tuple[CurrentPrice, ...]:
        normalized = normalize_symbols(symbols)
        payload = await self._parent.request(
            "GET", "/api/v1/prices", params={"symbols": ",".join(normalized)}
        )
        return tuple(parse_current_price(row) for row in result_list(payload))

    async def candles(
        self,
        symbol: str,
        *,
        interval: CandleInterval,
        count: int = 100,
        before: datetime | str | None = None,
        adjusted: bool = True,
    ) -> CandlePage:
        normalized_symbol = normalize_symbols([symbol], max_symbols=1)[0]
        if interval not in ("1m", "1d"):
            raise ValueError("interval must be '1m' or '1d'")
        if not 1 <= count <= 200:
            raise ValueError("count must be between 1 and 200")
        params = {
            "symbol": normalized_symbol,
            "interval": interval,
            "count": str(count),
            "adjusted": str(adjusted).lower(),
        }
        if before is not None:
            params["before"] = (
                before.isoformat() if isinstance(before, datetime) else before
            )
        payload = await self._parent.request("GET", "/api/v1/candles", params=params)
        return parse_candle_page(payload, symbol=normalized_symbol)

    async def kr_market_calendar(
        self, *, date: date | str | None = None
    ) -> KrMarketCalendar:
        payload = await self._parent.request(
            "GET", "/api/v1/market-calendar/KR", params=_calendar_params(date)
        )
        return parse_kr_market_calendar(payload)

    async def us_market_calendar(
        self, *, date: date | str | None = None
    ) -> UsMarketCalendar:
        payload = await self._parent.request(
            "GET", "/api/v1/market-calendar/US", params=_calendar_params(date)
        )
        return parse_us_market_calendar(payload)


def _calendar_params(value: date | str | None) -> dict[str, str] | None:
    if value is None:
        return None
    return {"date": value if isinstance(value, str) else value.isoformat()}


def normalize_symbols(
    symbols: str | Iterable[str], *, max_symbols: int = 200
) -> tuple[str, ...]:
    values = symbols.split(",") if isinstance(symbols, str) else list(symbols)
    normalized = tuple(value.strip().upper() for value in values if value.strip())
    if not normalized:
        raise ValueError("at least one symbol is required")
    if len(normalized) > max_symbols:
        raise ValueError(f"at most {max_symbols} symbols are allowed")
    invalid = [symbol for symbol in normalized if not _SYMBOL_PATTERN.fullmatch(symbol)]
    if invalid:
        raise ValueError(f"invalid symbol: {invalid[0]}")
    return normalized
