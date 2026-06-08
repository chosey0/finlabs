"""KIS market-data adapter calls.

This module owns KIS-specific market-data validation and SDK dispatch. It does
not persist results or know about CLI/FastAPI/Streamlit callers; orchestration
and transport layers decide whether and where fetched bars are stored.
"""

from __future__ import annotations

from modules.brokers.kis import (
    KisClient,
    OhlcvBar,
    OVERSEAS_MARKET_CODES,
    OverseasMinuteBar,
)
from modules.brokers.kis.parsers import parse_date


def normalize_period(period: str) -> str:
    """Normalize a KIS overseas period code."""

    normalized = period.strip().upper()
    if normalized not in {"D", "W", "M", "Y"}:
        raise ValueError("period must be one of: D, W, M, Y")
    return normalized


def period_to_interval(period: str) -> str:
    """Map a KIS period code to FinLabs' warehouse interval string."""

    return {"D": "1d", "W": "1w", "M": "1mo", "Y": "1y"}[normalize_period(period)]


async def fetch_ohlcv_history(
    client: KisClient,
    *,
    market: str,
    symbol: str,
    start: str,
    end: str,
    period: str,
    adjusted: bool,
    max_pages: int,
) -> list[OhlcvBar]:
    """Fetch overseas daily/weekly/monthly OHLCV bars via the KIS SDK."""

    normalized_period = normalize_period(period)
    if parse_date(start) > parse_date(end):
        raise ValueError("start must be on or before end")
    if market in {"KOSPI", "KOSDAQ"}:
        raise ValueError(
            "KIS data queries support overseas stocks only; use Kiwoom for domestic stocks"
        )
    if market not in OVERSEAS_MARKET_CODES:
        raise ValueError("KIS data queries support overseas stock markets only")
    if normalized_period == "Y":
        raise ValueError("overseas stock period price supports only D, W, or M")
    return await client.overseas.chart.daily(
        symbol,
        exchange=OVERSEAS_MARKET_CODES[market].upper(),  # type: ignore[arg-type]
        start=start,
        end=end,
        period=normalized_period,  # type: ignore[arg-type]
        market=market,
        adjusted=adjusted,
        max_pages=max_pages,
    )


async def fetch_overseas_minutes(
    client: KisClient,
    *,
    market: str,
    symbol: str,
    start: str,
    interval_minutes: int,
    count: int,
    include_previous: bool,
) -> list[OverseasMinuteBar]:
    """Fetch overseas minute bars via the KIS SDK."""

    if market not in OVERSEAS_MARKET_CODES:
        raise ValueError("overseas minute bars support overseas stock markets only")
    return await client.overseas.chart.minute(
        symbol,
        exchange=OVERSEAS_MARKET_CODES[market].upper(),  # type: ignore[arg-type]
        start=start,
        interval_minutes=interval_minutes,
        count=count,
        include_previous=include_previous,
        market=market,
    )
