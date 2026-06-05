"""Broker-agnostic warehouse query use cases."""

from __future__ import annotations

from pathlib import Path

from modules.domain.market_data import CandleBar
from modules.storage.repositories import (
    list_available_series as _list_available_series,
)
from modules.storage.repositories import (
    load_candles as _load_candles,
)


def load_candles(
    warehouse_path: str | Path,
    *,
    market: str,
    symbol: str,
    interval: str,
    limit: int | None = None,
) -> tuple[CandleBar, ...]:
    """Load canonical candles from storage."""

    return _load_candles(
        warehouse_path,
        market=market,
        symbol=symbol,
        interval=interval,
        limit=limit,
    )


def list_available_series(warehouse_path: str | Path) -> list[dict[str, str]]:
    """List stored candle series without broker-specific logic."""

    return _list_available_series(warehouse_path)

