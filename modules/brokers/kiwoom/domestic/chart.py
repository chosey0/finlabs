"""Kiwoom domestic stock chart APIs."""

from __future__ import annotations

from datetime import date as Date
from typing import TYPE_CHECKING, Any

from modules.brokers.kiwoom._internal.http import HttpResponse
from modules.brokers.kiwoom.endpoints.registry import lookup
from modules.brokers.kiwoom.models.ohlcv import ChartBar
from modules.brokers.kiwoom.parsers.rest import chart_rows, format_date, parse_chart_bar, parse_date

if TYPE_CHECKING:
    from modules.brokers.kiwoom.client import KiwoomClient

_TICK_SPEC = lookup("domestic.chart.tick")
_MINUTE_SPEC = lookup("domestic.chart.minute")
_DAILY_SPEC = lookup("domestic.chart.daily")
_WEEKLY_SPEC = lookup("domestic.chart.weekly")
_MONTHLY_SPEC = lookup("domestic.chart.monthly")
_YEARLY_SPEC = lookup("domestic.chart.yearly")

_MINUTE_SCOPES = {1, 3, 5, 10, 15, 30, 45, 60}
_TICK_SCOPES = {1, 3, 5, 10, 30}


class DomesticChartAPI:
    """High-level Kiwoom domestic stock chart client."""

    def __init__(self, parent: "KiwoomClient") -> None:
        self._parent = parent

    async def tick(
        self,
        symbol: str,
        *,
        tick_scope: int = 1,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int = 1,
    ) -> list[ChartBar]:
        """Fetch tick chart rows from ``ka10079``."""
        if tick_scope not in _TICK_SCOPES:
            raise ValueError("tick_scope must be one of: 1, 3, 5, 10, 30")
        return await self._fetch_chart(
            spec=_TICK_SPEC,
            chart_type="tick",
            symbol=symbol,
            market=market,
            interval=f"{tick_scope}tick",
            body={
                "stk_cd": _normalize_symbol(symbol),
                "tic_scope": str(tick_scope),
                "upd_stkpc_tp": "1" if adjusted else "0",
            },
            max_pages=max_pages,
        )

    async def minute(
        self,
        symbol: str,
        *,
        interval_minutes: int = 1,
        base_date: str | Date | None = None,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int = 1,
    ) -> list[ChartBar]:
        """Fetch minute chart rows from ``ka10080``."""
        if interval_minutes not in _MINUTE_SCOPES:
            raise ValueError(
                "interval_minutes must be one of: 1, 3, 5, 10, 15, 30, 45, 60"
            )
        body = {
            "stk_cd": _normalize_symbol(symbol),
            "tic_scope": str(interval_minutes),
            "upd_stkpc_tp": "1" if adjusted else "0",
        }
        if base_date is not None:
            body["base_dt"] = _format_optional_date(base_date)
        return await self._fetch_chart(
            spec=_MINUTE_SPEC,
            chart_type="minute",
            symbol=symbol,
            market=market,
            interval=f"{interval_minutes}min",
            body=body,
            max_pages=max_pages,
        )

    async def daily(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int = 1,
    ) -> list[ChartBar]:
        """Fetch daily chart rows from ``ka10081``."""
        return await self._period_chart(
            spec=_DAILY_SPEC,
            chart_type="daily",
            symbol=symbol,
            base_date=base_date,
            adjusted=adjusted,
            market=market,
            interval="1d",
            max_pages=max_pages,
        )

    async def weekly(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int = 1,
    ) -> list[ChartBar]:
        """Fetch weekly chart rows from ``ka10082``."""
        return await self._period_chart(
            spec=_WEEKLY_SPEC,
            chart_type="weekly",
            symbol=symbol,
            base_date=base_date,
            adjusted=adjusted,
            market=market,
            interval="1w",
            max_pages=max_pages,
        )

    async def monthly(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int = 1,
    ) -> list[ChartBar]:
        """Fetch monthly chart rows from ``ka10083``."""
        return await self._period_chart(
            spec=_MONTHLY_SPEC,
            chart_type="monthly",
            symbol=symbol,
            base_date=base_date,
            adjusted=adjusted,
            market=market,
            interval="1mo",
            max_pages=max_pages,
        )

    async def yearly(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int = 1,
    ) -> list[ChartBar]:
        """Fetch yearly chart rows from ``ka10094``."""
        return await self._period_chart(
            spec=_YEARLY_SPEC,
            chart_type="yearly",
            symbol=symbol,
            base_date=base_date,
            adjusted=adjusted,
            market=market,
            interval="1y",
            max_pages=max_pages,
        )

    async def _period_chart(
        self,
        *,
        spec,
        chart_type: str,
        symbol: str,
        base_date: str | Date,
        adjusted: bool,
        market: str,
        interval: str,
        max_pages: int,
    ) -> list[ChartBar]:
        return await self._fetch_chart(
            spec=spec,
            chart_type=chart_type,
            symbol=symbol,
            market=market,
            interval=interval,
            body={
                "stk_cd": _normalize_symbol(symbol),
                "base_dt": _format_optional_date(base_date),
                "upd_stkpc_tp": "1" if adjusted else "0",
            },
            max_pages=max_pages,
        )

    async def _fetch_chart(
        self,
        *,
        spec,
        chart_type: str,
        symbol: str,
        market: str,
        interval: str,
        body: dict[str, Any],
        max_pages: int,
    ) -> list[ChartBar]:
        normalized_symbol = _normalize_symbol(symbol)
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        bars: dict[str, ChartBar] = {}
        cont_yn = "N"
        next_key = ""
        seen_next_keys: set[tuple[str, str]] = set()

        for _ in range(max_pages):
            response = await self._parent.request_raw(
                spec,
                json_body=body,
                cont_yn=cont_yn,
                next_key=next_key,
            )
            for row in chart_rows(response.payload, chart_type):
                bar = parse_chart_bar(
                    market=market,
                    symbol=normalized_symbol,
                    interval=interval,
                    row=row,
                )
                bars[bar.timestamp] = bar

            next_cont_yn, next_key = _continuation(response)
            if next_cont_yn != "Y" or not next_key:
                break
            cursor = (next_cont_yn, next_key)
            if cursor in seen_next_keys:
                break
            seen_next_keys.add(cursor)
            cont_yn = next_cont_yn

        return sorted(bars.values(), key=lambda bar: bar.timestamp)


def _normalize_symbol(symbol: str) -> str:
    normalized = symbol.strip().upper()
    if not normalized:
        raise ValueError("symbol must not be empty")
    return normalized


def _format_optional_date(value: str | Date) -> str:
    if isinstance(value, Date):
        return format_date(value)
    return format_date(parse_date(value))


def _continuation(response: HttpResponse) -> tuple[str, str]:
    headers = {key.lower(): value for key, value in response.headers.items()}
    cont_yn = str(headers.get("cont-yn") or "").strip().upper()
    next_key = str(headers.get("next-key") or "").strip()
    return cont_yn, next_key
