"""Direct, lock-aware reads of the DuckDB warehouse for the dashboard.

DuckDB's "single writer + multiple readers" guarantee holds only *within one
process*. The warehouse writer runs in a separate process (the job server) and
holds an exclusive file lock while a collection job writes. A read_only reader in
this (Streamlit) process can therefore hit ``Conflicting lock`` mid-write. We
absorb that transient window with a bounded retry/backoff rather than failing the
page. Writes are short (insert-only), so a few attempts over ~1s cover it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, TypeVar

import duckdb

from research.tokenizers.data import CandleBar, load_candles

T = TypeVar("T")

_LOCK_HINT = "conflicting lock"
DEFAULT_RETRIES = 3
DEFAULT_BACKOFF_SECONDS = 0.4


class WarehouseBusyError(RuntimeError):
    """Raised when the warehouse stayed write-locked across all retries."""


def _is_lock_error(exc: Exception) -> bool:
    return _LOCK_HINT in str(exc).lower()


def with_lock_retry(
    operation: Callable[[], T],
    *,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``operation`` against the warehouse, retrying on transient write locks.

    This is the single sanctioned choke point for dashboard reads: any page that
    touches the warehouse should route through it so lock-retry coverage stays
    uniform (raising ``WarehouseBusyError`` only after all retries are exhausted).
    """
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return operation()
        except duckdb.Error as exc:
            if not _is_lock_error(exc):
                raise
            last_exc = exc
            if attempt < retries - 1:
                sleep(backoff * (attempt + 1))
    raise WarehouseBusyError(
        "warehouse is busy (collection in progress); please retry shortly"
    ) from last_exc


def read_candles_with_retry(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[CandleBar, ...]:
    """Load candles, retrying briefly if the warehouse is write-locked."""
    return with_lock_retry(
        lambda: load_candles(
            warehouse_path,
            market=market,
            symbol=symbol,
            interval=interval,
            limit=limit,
        ),
        retries=retries,
        backoff=backoff,
        sleep=sleep,
    )


def list_available_series(
    warehouse_path: str | Path,
    *,
    retries: int = DEFAULT_RETRIES,
    backoff: float = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, str]]:
    """Return distinct (market, symbol, interval) series stored in the warehouse.

    Combines daily ``ohlcv_bars`` and ``overseas_minute_bars`` so the chart page
    can offer only series that actually exist.
    """
    path = Path(warehouse_path).expanduser()
    if not path.exists():
        return []

    def _query() -> list[dict[str, str]]:
        with duckdb.connect(str(path), read_only=True) as connection:
            tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
            series: list[dict[str, str]] = []
            if "ohlcv_bars" in tables:
                rows = connection.execute(
                    "SELECT DISTINCT market, symbol, interval FROM ohlcv_bars"
                ).fetchall()
                series.extend({"market": m, "symbol": s, "interval": i} for m, s, i in rows)
            if "overseas_minute_bars" in tables:
                rows = connection.execute(
                    "SELECT DISTINCT market, symbol, interval_minutes FROM overseas_minute_bars"
                ).fetchall()
                series.extend(
                    {"market": m, "symbol": s, "interval": f"{int(mins)}m"} for m, s, mins in rows
                )
            return sorted(series, key=lambda r: (r["symbol"], r["interval"]))

    return with_lock_retry(_query, retries=retries, backoff=backoff, sleep=sleep)
