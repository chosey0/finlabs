from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from kis_cli.core.chart import OhlcvBar, bar_to_db_values, fetch_ohlcv_history, normalize_period
from kis_cli.services.auth import call_with_token_refresh_retry
from kis_cli.storage import (
    connect,
    connect_supabase,
    default_app_database_file,
    default_database_file,
    init_app_database,
    init_database,
    insert_supabase_ohlcv_bars,
)
from kis_cli.storage.app_repositories import finish_ingest_run, record_api_log, start_ingest_run
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
    store: str = "duckdb"


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
    store: str = "duckdb",
    supabase_dsn: str | None = None,
    adjusted: bool = True,
    max_pages: int = 100,
) -> ChartHistoryResult:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    normalized_store = _normalize_store(store)
    if save and normalized_store == "supabase" and db_path is not None:
        raise ValueError("--db-path is only valid with --store duckdb")
    resolved_market = resolve_symbol_market(normalized_symbol, db_path=db_path)
    resolved_end = end or date.today().isoformat()
    interval = _period_to_interval(period)
    init_result = init_database(db_path) if save and normalized_store == "duckdb" else None
    initialized_path = init_result.path if init_result else None
    run_id: int | None = None
    app_path = None
    if save:
        app_path = init_result.app_path if init_result else init_app_database(default_app_database_file())
        run_id = start_ingest_run(
            app_path,
            kind=f"ohlcv:{interval}",
            market=resolved_market,
            symbol=normalized_symbol,
        )

    try:
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
        stored = 0
        if save:
            values = [bar_to_db_values(bar) for bar in bars]
            if normalized_store == "supabase":
                with connect_supabase(dsn=supabase_dsn) as connection:
                    stored = insert_supabase_ohlcv_bars(connection, values)
            else:
                with connect(init_result.path) as connection:
                    stored = insert_ohlcv_bars(connection, values)
            finish_ingest_run(
                app_path,
                run_id,
                status="success",
                rows_written=stored,
            )
            record_api_log(
                app_path,
                endpoint=f"ohlcv:{resolved_market}:{interval}",
                status_code=200,
            )
    except Exception as exc:
        if save and app_path is not None and run_id is not None:
            message = str(exc)
            finish_ingest_run(
                app_path,
                run_id,
                status="failed",
                error=message,
            )
            record_api_log(
                app_path,
                endpoint=f"ohlcv:{resolved_market}:{interval}",
                error=message,
            )
        raise

    return ChartHistoryResult(
        db_path=initialized_path,
        market=bars[0].market if bars else resolved_market,
        symbol=bars[0].symbol if bars else normalized_symbol,
        interval=interval,
        fetched=len(bars),
        stored=stored,
        bars=bars,
        store=normalized_store,
    )


def resolve_symbol_market(symbol: str, *, db_path: Path | None = None) -> str:
    path = (db_path or default_database_file()).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"symbol warehouse not found at {path}; run 'kiscli symbols download' first"
        )
    try:
        with connect(path) as connection:
            markets = list(find_symbol_markets(connection, symbol=symbol))
    except duckdb.Error as exc:
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


def _normalize_store(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"duckdb", "supabase"}:
        raise ValueError("store must be one of: duckdb, supabase")
    return normalized
