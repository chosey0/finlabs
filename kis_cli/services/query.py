from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

from kis import parse_minute_datetime

from kis_cli.storage import connect
from kis_cli.storage.repositories import query_daily_ohlcv_bars, query_overseas_minute_bars

DAILY_INTERVAL = "1d"


@dataclass(frozen=True)
class OhlcvQueryResult:
    db_path: Path | None
    symbol: str
    interval: str
    start: str | None
    end: str | None
    rows: list[dict[str, object]]


def query_stored_daily_ohlcv(
    *,
    symbol: str,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = 20,
    db_path: Path | None = None,
) -> OhlcvQueryResult:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    normalized_start = normalize_query_date(start) if start else None
    normalized_end = normalize_query_date(end) if end else None
    if normalized_start and normalized_end and normalized_start > normalized_end:
        raise ValueError("start must be on or before end")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    with connect(db_path) as connection:
        rows = query_daily_ohlcv_bars(
            connection,
            symbol=normalized_symbol,
            start=normalized_start,
            end=normalized_end,
            limit=limit,
        )

    return OhlcvQueryResult(
        db_path=db_path,
        symbol=normalized_symbol,
        interval=DAILY_INTERVAL,
        start=normalized_start,
        end=normalized_end,
        rows=list(rows),
    )


@dataclass(frozen=True)
class OverseasMinuteQueryResult:
    db_path: Path | None
    symbol: str
    interval_minutes: int | None
    start: str | None
    end: str | None
    rows: list[dict[str, object]]


def query_stored_overseas_minutes(
    *,
    symbol: str,
    interval_minutes: int | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = 20,
    db_path: Path | None = None,
) -> OverseasMinuteQueryResult:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    if interval_minutes is not None and interval_minutes < 1:
        raise ValueError("interval minutes must be at least 1")
    if limit is not None and limit < 1:
        raise ValueError("limit must be at least 1")

    start_bound = classify_minute_query_bound(start) if start else None
    end_bound = classify_minute_query_bound(end) if end else None
    if start_bound is not None and end_bound is not None:
        if _minute_bound_sort_key(start_bound) > _minute_bound_sort_key(end_bound):
            raise ValueError("start must be on or before end")

    with connect(db_path) as connection:
        rows = query_overseas_minute_bars(
            connection,
            symbol=normalized_symbol,
            interval_minutes=interval_minutes,
            start_bound=start_bound,
            end_bound=end_bound,
            limit=limit,
        )

    return OverseasMinuteQueryResult(
        db_path=db_path,
        symbol=normalized_symbol,
        interval_minutes=interval_minutes,
        start=start.strip() if start else None,
        end=end.strip() if end else None,
        rows=list(rows),
    )


def classify_minute_query_bound(value: str) -> tuple[Literal["date", "ts"], str]:
    text = value.strip().replace("T", " ")
    if not text:
        raise ValueError("boundary must not be empty")
    if len(text) == 8 and text.isdigit():
        return ("date", normalize_query_date(text))
    try:
        dt = parse_minute_datetime(text)
    except ValueError:
        return ("date", normalize_query_date(text))
    if " " in text or (text.isdigit() and len(text) > 8):
        return ("ts", dt.strftime("%Y-%m-%d %H:%M:%S"))
    return ("date", dt.date().isoformat())


def _minute_bound_sort_key(bound: tuple[str, str]) -> datetime:
    kind, val = bound
    if kind == "date":
        return datetime.combine(date.fromisoformat(val), time.min)
    return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")


def normalize_query_date(value: str) -> str:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return date.fromisoformat(text).isoformat()
