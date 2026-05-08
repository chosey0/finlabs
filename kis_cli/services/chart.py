from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from kis_cli.config.resolver import resolve_profile
from kis_cli.core.chart import OhlcvBar, bar_to_db_values, fetch_ohlcv_history, normalize_period
from kis_cli.services.auth import call_with_token_refresh_retry
from kis_cli.storage import connect, default_database_file, init_database
from kis_cli.storage.repositories import find_symbol_markets, insert_ohlcv_bars


@dataclass(frozen=True)
class ChartHistoryResult:
    db_path: Path | None
    market: str
    symbol: str
    interval: str
    fetched: int
    stored: int
    bars: list[OhlcvBar]


def collect_ohlcv_history(
    *,
    symbol: str,
    start: str,
    end: str | None,
    period: str,
    profile: str | None = None,
    config_path: Path | None = None,
    db_path: Path | None = None,
    save: bool = False,
    adjusted: bool = True,
    max_pages: int = 100,
) -> ChartHistoryResult:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    resolved_market = resolve_symbol_market(normalized_symbol, db_path=db_path)
    resolved_end = end or date.today().isoformat()

    bars = call_with_token_refresh_retry(
        lambda client: fetch_ohlcv_history(
            client,
            market=resolved_market,
            symbol=normalized_symbol,
            start=start,
            end=resolved_end,
            period=period,
            adjusted=adjusted,
            max_pages=max_pages,
        ),
        profile=profile,
        config_path=config_path,
    )
    interval = _period_to_interval(period)
    stored = 0
    initialized_path: Path | None = None
    if save:
        init_result = init_database(db_path)
        initialized_path = init_result.path
        with connect(init_result.path) as connection:
            stored = insert_ohlcv_bars(
                connection,
                (bar_to_db_values(bar) for bar in bars),
            )

    return ChartHistoryResult(
        db_path=initialized_path,
        market=bars[0].market if bars else resolved_market,
        symbol=bars[0].symbol if bars else normalized_symbol,
        interval=interval,
        fetched=len(bars),
        stored=stored,
        bars=bars,
    )


def resolve_symbol_market(symbol: str, *, db_path: Path | None = None) -> str:
    path = (db_path or default_database_file()).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"symbol database not found at {path}; run 'kiscli symbols download' first"
        )
    try:
        with connect(path) as connection:
            markets = list(find_symbol_markets(connection, symbol=symbol))
    except sqlite3.OperationalError as exc:
        raise ValueError(
            f"symbols table is not initialized in {path}; run 'kiscli symbols download' first"
        ) from exc
    if not markets:
        raise ValueError(f"symbol '{symbol}' not found in symbols table; run 'kiscli symbols download' first")
    if len(markets) > 1:
        joined = ", ".join(markets)
        raise ValueError(f"symbol '{symbol}' matched multiple markets: {joined}")
    return markets[0]


def _period_to_interval(period: str) -> str:
    return {"D": "1d", "W": "1w", "M": "1mo", "Y": "1y"}[normalize_period(period)]
