from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from kis_cli.storage import connect
from kis_cli.storage.repositories import query_daily_ohlcv_bars

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
        rows=[dict(row) for row in rows],
    )


def normalize_query_date(value: str) -> str:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date().isoformat()
    return date.fromisoformat(text).isoformat()
