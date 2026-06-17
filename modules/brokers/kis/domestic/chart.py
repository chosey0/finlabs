"""Domestic stock minute chart APIs."""

from __future__ import annotations

from datetime import date as Date
from datetime import time as Time
from typing import TYPE_CHECKING, Literal

from modules.brokers.kis._internal.pacing import ContinuationPacer, call_with_continuation_pacing
from modules.brokers.kis.endpoints.registry import lookup
from modules.brokers.kis.models.ohlcv import DomesticMinuteBar
from modules.brokers.kis.parsers.rest import format_date, output_rows, parse_date, parse_domestic_minute_bar

if TYPE_CHECKING:
    from modules.brokers.kis.client import KisClient

DomesticMarketCode = Literal["J", "NX", "UN"]

_MINUTE_SPEC = lookup("domestic.chart.minute")
_MARKET_LABELS: dict[DomesticMarketCode, str] = {
    "J": "KRX",
    "NX": "NXT",
    "UN": "KRX+NXT",
}


class DomesticChartAPI:
    """High-level domestic stock chart client."""

    def __init__(self, parent: "KisClient") -> None:
        self._parent = parent

    async def minute(
        self,
        symbol: str,
        *,
        date: str | Date,
        end_time: str | Time = "15:30:00",
        start_time: str | Time = "00:00:00",
        market_code: DomesticMarketCode = "J",
        include_previous_data: bool = True,
        include_fake_ticks: bool = False,
        market: str | None = None,
        max_pages: int = 100,
    ) -> list[DomesticMinuteBar]:
        """Fetch one trading day's minute bars in ascending time order.

        KIS returns at most 120 rows in reverse chronological order. The
        earliest returned time becomes the next request cursor. Inclusive
        boundary rows are deduplicated before the final ascending sort.
        """
        normalized_symbol = symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol must not be empty")
        if market_code not in _MARKET_LABELS:
            raise ValueError("market_code must be one of: J, NX, UN")
        if max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        target_date = date if isinstance(date, Date) else parse_date(date)
        start_cursor = _format_time(start_time, field_name="start_time")
        page_cursor = _format_time(end_time, field_name="end_time")
        if start_cursor > page_cursor:
            raise ValueError("start_time must be on or before end_time")

        market_label = market or _MARKET_LABELS[market_code]
        target_date_text = format_date(target_date)
        bars: dict[tuple[str, str], DomesticMinuteBar] = {}
        seen_cursors: set[str] = set()
        pacer = ContinuationPacer()

        for _ in range(max_pages):
            if page_cursor in seen_cursors:
                break
            seen_cursors.add(page_cursor)

            payload = await call_with_continuation_pacing(
                pacer,
                lambda: self._parent.request(
                    _MINUTE_SPEC,
                    params={
                        "FID_COND_MRKT_DIV_CODE": market_code,
                        "FID_INPUT_ISCD": normalized_symbol,
                        "FID_INPUT_HOUR_1": page_cursor,
                        "FID_INPUT_DATE_1": target_date_text,
                        "FID_PW_DATA_INCU_YN": "Y" if include_previous_data else "N",
                        "FID_FAKE_TICK_INCU_YN": "Y" if include_fake_ticks else "N",
                    },
                ),
            )
            rows = output_rows(payload)
            parsed = [
                parse_domestic_minute_bar(
                    market=market_label,
                    symbol=normalized_symbol,
                    row=row,
                )
                for row in rows
            ]
            target_bars = [
                bar
                for bar in parsed
                if bar.business_date == target_date.isoformat()
                and start_cursor <= _compact_time(bar.time) <= page_cursor
            ]
            for bar in target_bars:
                bars[(bar.business_date, bar.time)] = bar

            page_times = [_compact_time(bar.time) for bar in parsed]
            if not page_times:
                break
            earliest_time = min(page_times)
            if earliest_time <= start_cursor:
                break
            page_cursor = earliest_time

        return sorted(bars.values(), key=lambda bar: (bar.business_date, bar.time))


def _format_time(value: str | Time, *, field_name: str) -> str:
    if isinstance(value, Time):
        return value.strftime("%H%M%S")
    digits = value.strip().replace(":", "")
    if len(digits) not in (4, 6) or not digits.isdigit():
        raise ValueError(f"{field_name} must be HH:MM[:SS] or HHMMSS")
    if len(digits) == 4:
        digits += "00"
    try:
        Time.fromisoformat(f"{digits[0:2]}:{digits[2:4]}:{digits[4:6]}")
    except ValueError as exc:
        raise ValueError(f"{field_name} must be a valid time") from exc
    return digits


def _compact_time(value: str) -> str:
    return value.replace(":", "")
