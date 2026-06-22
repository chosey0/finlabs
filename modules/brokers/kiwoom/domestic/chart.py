"""Kiwoom domestic stock chart APIs."""

from __future__ import annotations

import asyncio
import calendar
from datetime import date as Date
from datetime import datetime
from typing import TYPE_CHECKING, Any

from modules.brokers.kiwoom._internal.http import HttpResponse
from modules.brokers.kiwoom.endpoints.registry import lookup
from modules.brokers.kiwoom.exceptions import KiwoomApiError
from modules.brokers.kiwoom.models.ohlcv import ChartBar
from modules.brokers.kiwoom.parsers.rest import (
    chart_rows,
    format_date,
    parse_chart_bar,
    parse_date,
)

if TYPE_CHECKING:
    from modules.brokers.kiwoom.client import KiwoomClient

_TICK_SPEC = lookup("domestic.chart.tick")
_MINUTE_SPEC = lookup("domestic.chart.minute")
_INDUSTRY_MINUTE_SPEC = lookup("domestic.chart.industry_minute")
_DAILY_SPEC = lookup("domestic.chart.daily")
_WEEKLY_SPEC = lookup("domestic.chart.weekly")
_MONTHLY_SPEC = lookup("domestic.chart.monthly")
_YEARLY_SPEC = lookup("domestic.chart.yearly")

_MINUTE_SCOPES = {1, 3, 5, 10, 15, 30, 45, 60}
_TICK_SCOPES = {1, 3, 5, 10, 30}
_RATE_LIMIT_RETRY_DELAYS = (1.0, 2.0, 4.0)


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
        max_pages: int | None = None,
        start_date: str | None = None,
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
            start_date=start_date,
            end_date=None,
        )

    async def minute(
        self,
        symbol: str,
        *,
        interval_minutes: int = 1,
        base_date: str | Date | None = None,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int | None = None,
        start_date: str | None = None,
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
            start_date=start_date,
            end_date=base_date,
        )

    async def industry_minute(
        self,
        index_code: str,
        *,
        interval_minutes: int = 1,
        base_date: str | Date | None = None,
        max_pages: int | None = None,
        start_date: str | None = None,
    ) -> list[ChartBar]:
        """Fetch industry minute rows from ``ka20005``."""
        if interval_minutes not in _MINUTE_SCOPES:
            raise ValueError(
                "interval_minutes must be one of: 1, 3, 5, 10, 15, 30, 45, 60"
            )
        body = {
            "inds_cd": _normalize_symbol(index_code),
            "tic_scope": str(interval_minutes),
        }
        if base_date is not None:
            body["base_dt"] = _format_optional_date(base_date)
        return await self._fetch_chart(
            spec=_INDUSTRY_MINUTE_SPEC,
            chart_type="industry_minute",
            symbol=index_code,
            market="KRX-INDEX",
            interval=f"{interval_minutes}min",
            body=body,
            max_pages=max_pages,
            start_date=start_date,
            end_date=base_date,
        )

    async def daily(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int | None = None,
        start_date: str | None = None,
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
            start_date=start_date,
        )

    async def weekly(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int | None = None,
        start_date: str | None = None,
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
            start_date=start_date,
        )

    async def monthly(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int | None = None,
        start_date: str | None = None,
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
            start_date=start_date,
        )

    async def yearly(
        self,
        symbol: str,
        *,
        base_date: str | Date,
        adjusted: bool = True,
        market: str = "KRX",
        max_pages: int | None = None,
        start_date: str | None = None,
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
            start_date=start_date,
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
        max_pages: int | None,
        start_date: str | None,
    ) -> list[ChartBar]:
        return await self._fetch_chart(
            spec=spec,
            chart_type=chart_type,
            symbol=symbol,
            market=market,
            interval=interval,
            body={
                "stk_cd": _normalize_symbol(symbol),
                "base_dt": _format_base_date(chart_type, base_date),
                "upd_stkpc_tp": "1" if adjusted else "0",
            },
            max_pages=max_pages,
            start_date=start_date,
            end_date=base_date,
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
        max_pages: int | None,
        start_date: str | None,
        end_date: str | Date | None,
    ) -> list[ChartBar]:
        normalized_symbol = _normalize_symbol(symbol)
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be at least 1")
        start_key = _boundary_key(chart_type, start_date) if start_date else None
        end_key = _end_boundary_key(chart_type, end_date)
        if start_key and end_key and start_key > end_key:
            raise ValueError("start_date must be on or before base_date")

        bars: dict[str, ChartBar] = {}
        cont_yn = "N"
        next_key = ""
        seen_next_keys: set[tuple[str, str]] = set()
        page_count = 0

        while max_pages is None or page_count < max_pages:
            response = await _request_with_rate_limit_retry(
                self._parent,
                spec,
                json_body=body,
                cont_yn=cont_yn,
                next_key=next_key,
            )
            page_count += 1
            page_keys: list[str] = []
            for row in chart_rows(response.payload, chart_type):
                bar = parse_chart_bar(
                    market=market,
                    symbol=normalized_symbol,
                    interval=interval,
                    row=row,
                )
                key = _bar_boundary_key(chart_type, bar)
                page_keys.append(key)
                if start_key and key < start_key:
                    continue
                if end_key and key > end_key:
                    continue
                bars[bar.timestamp] = bar

            if start_key and page_keys and min(page_keys) <= start_key:
                break

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


def _format_base_date(chart_type: str, value: str | Date) -> str:
    if isinstance(value, Date):
        return format_date(value)
    text = value.strip()
    if chart_type == "monthly" and _is_year_month(text):
        year = int(text[:4])
        month = int(text[5:7])
        return f"{year:04d}{month:02d}{calendar.monthrange(year, month)[1]:02d}"
    if chart_type == "yearly" and _is_year(text):
        return f"{int(text):04d}1231"
    return _format_optional_date(value)


def _continuation(response: HttpResponse) -> tuple[str, str]:
    headers = {key.lower(): value for key, value in response.headers.items()}
    cont_yn = str(headers.get("cont-yn") or "").strip().upper()
    next_key = str(headers.get("next-key") or "").strip()
    return cont_yn, next_key


async def _request_with_rate_limit_retry(
    parent: "KiwoomClient",
    spec,
    *,
    json_body: dict[str, Any],
    cont_yn: str,
    next_key: str,
) -> HttpResponse:
    for attempt, delay_seconds in enumerate((*_RATE_LIMIT_RETRY_DELAYS, 0.0)):
        try:
            return await parent.request_raw(
                spec,
                json_body=json_body,
                cont_yn=cont_yn,
                next_key=next_key,
            )
        except KiwoomApiError as exc:
            if not _is_rate_limit_error(exc) or attempt >= len(
                _RATE_LIMIT_RETRY_DELAYS
            ):
                raise
            await asyncio.sleep(delay_seconds)
    raise RuntimeError("unreachable")


def _is_rate_limit_error(exc: KiwoomApiError) -> bool:
    values = (str(exc), exc.return_code or "", exc.return_msg or "")
    return any("1700" in value or "허용된 요청 개수" in value for value in values)


def _boundary_key(chart_type: str, value: str | None) -> str:
    if value is None:
        return ""
    text = value.strip()
    if not text:
        raise ValueError("start_date must not be empty")
    if chart_type in {"tick", "minute", "industry_minute"}:
        return _parse_boundary_datetime(text)
    if chart_type in {"daily", "weekly"}:
        return parse_date(text).isoformat()
    if chart_type == "monthly":
        if not _is_year_month(text):
            raise ValueError("monthly start_date must be YYYY-MM")
        return text
    if chart_type == "yearly":
        if not _is_year(text):
            raise ValueError("yearly start_date must be YYYY")
        return f"{int(text):04d}"
    raise ValueError(f"unsupported chart_type: {chart_type}")


def _end_boundary_key(chart_type: str, value: str | Date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Date):
        text = value.isoformat()
    else:
        text = value.strip()
    if not text:
        return None
    if chart_type in {"tick", "minute", "industry_minute"}:
        return f"{parse_date(text).isoformat()} 23:59:59"
    if chart_type in {"daily", "weekly"}:
        return parse_date(text).isoformat()
    if chart_type == "monthly":
        if _is_year_month(text):
            return text
        return parse_date(text).isoformat()[:7]
    if chart_type == "yearly":
        if _is_year(text):
            return f"{int(text):04d}"
        return parse_date(text).isoformat()[:4]
    raise ValueError(f"unsupported chart_type: {chart_type}")


def _bar_boundary_key(chart_type: str, bar: ChartBar) -> str:
    if chart_type in {"tick", "minute", "industry_minute"}:
        return _parse_boundary_datetime(bar.timestamp)
    if chart_type in {"daily", "weekly"}:
        return parse_date(bar.timestamp).isoformat()
    if chart_type == "monthly":
        return parse_date(bar.timestamp).isoformat()[:7]
    if chart_type == "yearly":
        return parse_date(bar.timestamp).isoformat()[:4]
    raise ValueError(f"unsupported chart_type: {chart_type}")


def _parse_boundary_datetime(value: str) -> str:
    text = value.strip()
    for datetime_format in (
        "%Y-%m-%d %H%M%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y-%m-%d %H:%M",
    ):
        try:
            return datetime.strptime(text, datetime_format).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            continue
    raise ValueError("tick/minute start_date must be YYYY-MM-DD HHMMSS")


def _is_year_month(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError:
        return False
    return True


def _is_year(value: str) -> bool:
    return len(value) == 4 and value.isdigit()
