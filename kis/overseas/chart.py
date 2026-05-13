"""Overseas OHLCV chart APIs.

Accessed via `client.overseas.chart`. Two endpoint families:

- ``daily(period="D"|"W"|"M")`` → KIS dailyprice (HHDFS76240000), paginates
  via ``KEYB`` token + backward ``BYMD``.
- ``minute(interval_minutes=N)`` → KIS minute chart (HHDFS76950200),
  paginates via ``output1.next`` flag + ``KEYB`` derived from the oldest
  parsed bar.

Both endpoints are mock-unsupported on KIS's side; the underlying
``EndpointSpec.tr_id_for("mock")`` will raise ``MockNotSupportedError``
when ``environment="mock"``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any, Literal

from kis.endpoints.registry import lookup
from kis.models.ohlcv import OhlcvBar, OverseasMinuteBar
from kis.parsers.rest import (
    date_value,
    format_date,
    output_rows,
    parse_date,
    parse_minute_datetime,
    parse_overseas_minute_bar,
    parse_overseas_ohlcv_bar,
)

if TYPE_CHECKING:
    from kis.client import KisClient

_DAILY_SPEC = lookup("overseas.chart.dailyprice")
_MINUTE_SPEC = lookup("overseas.chart.minute")

OverseasPeriod = Literal["D", "W", "M"]
OverseasExchangeCode = Literal[
    "NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS", "HNX", "HSX"
]

_PERIOD_TO_INTERVAL: dict[OverseasPeriod, str] = {"D": "1d", "W": "1w", "M": "1mo"}
_PERIOD_TO_GUBN: dict[OverseasPeriod, str] = {"D": "0", "W": "1", "M": "2"}
_DAILY_PAGE_SIZE = 100
_MINUTE_PAGE_SIZE = 120


class OverseasChartAPI:
    """High-level overseas OHLCV chart client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def daily(
        self,
        symbol: str,
        *,
        exchange: OverseasExchangeCode,
        start: str | date,
        end: str | date,
        period: OverseasPeriod = "D",
        market: str | None = None,
        adjusted: bool = True,
        max_pages: int = 100,
    ) -> list[OhlcvBar]:
        """Fetch overseas OHLCV bars for D / W / M period codes.

        The KIS dailyprice endpoint pages backward in time. We loop until
        the response covers `start` or `max_pages` is exhausted, then
        return deduplicated, ascending bars.
        """
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        normalized_exchange = exchange.strip().upper()
        market_label = market or normalized_exchange
        start_date = _coerce_date(start)
        end_date = _coerce_date(end)
        if start_date > end_date:
            raise ValueError("start must be on or before end")
        if period not in _PERIOD_TO_GUBN:
            raise ValueError("overseas daily chart supports period D, W, or M")
        interval = _PERIOD_TO_INTERVAL[period]

        bars: dict[str, OhlcvBar] = {}
        keyb = ""
        page_end = end_date

        for _ in range(max_pages):
            payload = await self._parent.request(
                _DAILY_SPEC,
                params={
                    "AUTH": "",
                    "EXCD": normalized_exchange,
                    "SYMB": normalized_symbol,
                    "GUBN": _PERIOD_TO_GUBN[period],
                    "BYMD": format_date(page_end),
                    "MODP": "1" if adjusted else "0",
                    "KEYB": keyb,
                },
            )
            rows = output_rows(payload)
            raw_dates = [parse_date(date_value(row, "xymd")) for row in rows]
            parsed = [
                bar
                for bar in (
                    parse_overseas_ohlcv_bar(
                        market=market_label,
                        symbol=normalized_symbol,
                        interval=interval,
                        row=row,
                    )
                    for row in rows
                )
                if start_date <= parse_date(bar.timestamp) <= end_date
            ]
            for bar in parsed:
                bars[bar.timestamp] = bar

            if raw_dates and min(raw_dates) <= start_date:
                break

            next_keyb = _next_keyb(payload)
            if next_keyb and next_keyb != keyb:
                keyb = next_keyb
                continue

            if len(rows) < _DAILY_PAGE_SIZE or not raw_dates:
                break

            next_page_end = min(raw_dates) - timedelta(days=1)
            if next_page_end >= page_end:
                break
            page_end = next_page_end
            keyb = ""

        return sorted(bars.values(), key=lambda bar: bar.timestamp)

    async def minute(
        self,
        symbol: str,
        *,
        exchange: OverseasExchangeCode,
        start: str | datetime,
        interval_minutes: int = 1,
        count: int = _MINUTE_PAGE_SIZE,
        include_previous: bool = True,
        market: str | None = None,
        max_pages: int = 100,
    ) -> list[OverseasMinuteBar]:
        """Fetch overseas minute bars until `start` (inclusive)."""
        if interval_minutes < 1:
            raise ValueError("interval_minutes must be at least 1")
        if not 1 <= count <= _MINUTE_PAGE_SIZE:
            raise ValueError(f"count must be between 1 and {_MINUTE_PAGE_SIZE}")
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        normalized_exchange = exchange.strip().upper()
        market_label = market or normalized_exchange
        start_at = (
            start if isinstance(start, datetime) else parse_minute_datetime(start)
        )

        bars: dict[tuple[str, str], OverseasMinuteBar] = {}
        next_value = ""
        keyb = ""
        seen_keybs: set[str] = set()

        for _ in range(max_pages):
            payload = await self._parent.request(
                _MINUTE_SPEC,
                params={
                    "AUTH": "",
                    "EXCD": normalized_exchange,
                    "SYMB": normalized_symbol,
                    "NMIN": str(interval_minutes),
                    "PINC": "1" if include_previous else "0",
                    "NEXT": next_value,
                    "NREC": str(count),
                    "FILL": "",
                    "KEYB": keyb,
                },
            )
            rows = output_rows(payload)
            parsed = [
                parse_overseas_minute_bar(
                    market=market_label,
                    symbol=normalized_symbol,
                    interval_minutes=interval_minutes,
                    row=row,
                )
                for row in rows
            ]
            for bar in parsed:
                if _minute_bar_datetime(bar) >= start_at:
                    bars[(bar.local_date, bar.local_time)] = bar

            if parsed and min(_minute_bar_datetime(bar) for bar in parsed) <= start_at:
                break
            if not _has_more_minute_data(payload) or not parsed:
                break
            keyb = _next_minute_keyb(parsed[-1], interval_minutes)
            if keyb in seen_keybs:
                break
            seen_keybs.add(keyb)
            next_value = "1"

        return sorted(bars.values(), key=lambda bar: (bar.local_date, bar.local_time))


def _coerce_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return parse_date(value)


def _next_keyb(payload: dict[str, Any]) -> str:
    for key in ("KEYB", "keyb"):
        value = str(payload.get(key) or "").strip()
        if value:
            return value
    output1 = payload.get("output1")
    if isinstance(output1, dict):
        for key in ("KEYB", "keyb"):
            value = str(output1.get(key) or "").strip()
            if value:
                return value
    return ""


def _has_more_minute_data(payload: dict[str, Any]) -> bool:
    output1 = payload.get("output1")
    if not isinstance(output1, dict):
        return False
    return str(output1.get("next") or "").strip() == "1"


def _next_minute_keyb(bar: OverseasMinuteBar, interval_minutes: int) -> str:
    return (_minute_bar_datetime(bar) - timedelta(minutes=interval_minutes)).strftime(
        "%Y%m%d%H%M%S"
    )


def _minute_bar_datetime(bar: OverseasMinuteBar) -> datetime:
    return datetime.strptime(
        f"{bar.local_date.replace('-', '')}{bar.local_time.replace(':', '')}",
        "%Y%m%d%H%M%S",
    )
