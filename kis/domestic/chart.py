"""Domestic OHLCV chart APIs (daily / weekly / monthly / yearly).

Accessed via `client.domestic.chart`. The underlying KIS endpoint paginates
backwards by `FID_INPUT_DATE_2`, so this module loops until the requested
`start` is reached or `max_pages` is exhausted, then returns a deduplicated,
ascending-sorted `list[OhlcvBar]`.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Literal

from kis._internal.pacing import ContinuationPacer, call_with_continuation_pacing
from kis.endpoints.registry import lookup
from kis.models.ohlcv import OhlcvBar
from kis.parsers.rest import (
    format_date,
    output_rows,
    parse_date,
    parse_domestic_ohlcv_bar,
)

if TYPE_CHECKING:
    from kis.client import KisClient

_SPEC = lookup("domestic.chart.ohlcv")

PeriodCode = Literal["D", "W", "M", "Y"]

_PERIOD_TO_INTERVAL: dict[PeriodCode, str] = {
    "D": "1d",
    "W": "1w",
    "M": "1mo",
    "Y": "1y",
}


class DomesticChartAPI:
    """High-level domestic OHLCV chart client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def daily(
        self,
        symbol: str,
        *,
        start: str | date,
        end: str | date,
        market: str = "KOSPI",
        adjusted: bool = True,
        max_pages: int = 100,
    ) -> list[OhlcvBar]:
        return await self._history(
            symbol,
            start=start,
            end=end,
            period="D",
            market=market,
            adjusted=adjusted,
            max_pages=max_pages,
        )

    async def weekly(
        self,
        symbol: str,
        *,
        start: str | date,
        end: str | date,
        market: str = "KOSPI",
        adjusted: bool = True,
        max_pages: int = 100,
    ) -> list[OhlcvBar]:
        return await self._history(
            symbol,
            start=start,
            end=end,
            period="W",
            market=market,
            adjusted=adjusted,
            max_pages=max_pages,
        )

    async def monthly(
        self,
        symbol: str,
        *,
        start: str | date,
        end: str | date,
        market: str = "KOSPI",
        adjusted: bool = True,
        max_pages: int = 100,
    ) -> list[OhlcvBar]:
        return await self._history(
            symbol,
            start=start,
            end=end,
            period="M",
            market=market,
            adjusted=adjusted,
            max_pages=max_pages,
        )

    async def yearly(
        self,
        symbol: str,
        *,
        start: str | date,
        end: str | date,
        market: str = "KOSPI",
        adjusted: bool = True,
        max_pages: int = 100,
    ) -> list[OhlcvBar]:
        return await self._history(
            symbol,
            start=start,
            end=end,
            period="Y",
            market=market,
            adjusted=adjusted,
            max_pages=max_pages,
        )

    async def _history(
        self,
        symbol: str,
        *,
        start: str | date,
        end: str | date,
        period: PeriodCode,
        market: str,
        adjusted: bool,
        max_pages: int,
    ) -> list[OhlcvBar]:
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        start_date = _coerce_date(start)
        end_date = _coerce_date(end)
        if start_date > end_date:
            raise ValueError("start must be on or before end")
        interval = _PERIOD_TO_INTERVAL[period]

        bars: dict[str, OhlcvBar] = {}
        page_end = end_date
        pacer = ContinuationPacer()

        for _ in range(max_pages):
            payload = await call_with_continuation_pacing(
                pacer,
                lambda: self._parent.request(
                    _SPEC,
                    params={
                        "FID_COND_MRKT_DIV_CODE": "J",
                        "FID_INPUT_ISCD": normalized_symbol,
                        "FID_INPUT_DATE_1": format_date(start_date),
                        "FID_INPUT_DATE_2": format_date(page_end),
                        "FID_PERIOD_DIV_CODE": period,
                        "FID_ORG_ADJ_PRC": "0" if adjusted else "1",
                    },
                ),
            )
            rows = output_rows(payload)
            parsed = [
                bar
                for bar in (
                    parse_domestic_ohlcv_bar(
                        market=market,
                        symbol=normalized_symbol,
                        interval=interval,
                        row=row,
                    )
                    for row in rows
                )
                if start_date <= parse_date(bar.timestamp) <= end_date
            ]
            if not parsed:
                break

            for bar in parsed:
                bars[bar.timestamp] = bar

            oldest = min(parse_date(bar.timestamp) for bar in parsed)
            if oldest <= start_date:
                break
            next_end = oldest - timedelta(days=1)
            if next_end >= page_end:
                break
            page_end = next_end

        return sorted(bars.values(), key=lambda bar: bar.timestamp)


def _coerce_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return parse_date(value)
