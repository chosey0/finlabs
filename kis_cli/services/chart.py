from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from kis import KisClient, OhlcvBar, OVERSEAS_MARKET_CODES, OverseasMinuteBar
from kis.parsers import parse_date

from kis_cli.services.auth import call_with_sdk_client
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
from kis_cli.storage.mappers import bar_to_db_values, minute_bar_to_db_values
from kis_cli.storage.repositories import find_symbol_markets, insert_ohlcv_bars, insert_overseas_minute_bars


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


@dataclass(frozen=True)
class OverseasMinuteResult:
    db_path: Path | None
    market: str
    symbol: str
    interval_minutes: int
    fetched: int
    stored: int
    bars: list[OverseasMinuteBar]


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
        bars = call_with_sdk_client(
            lambda client: _fetch_ohlcv_history_async(
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


def collect_overseas_minutes(
    *,
    symbol: str,
    start: str,
    interval_minutes: int = 1,
    count: int = 120,
    profile: str | None = None,
    config_path: Path | None = None,
    db_path: Path | None = None,
    save: bool = False,
    include_previous: bool = True,
) -> OverseasMinuteResult:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    resolved_market = resolve_symbol_market(normalized_symbol, db_path=db_path)
    init_result = init_database(db_path) if save else None
    initialized_path = init_result.path if init_result else None
    run_id: int | None = None
    if init_result:
        run_id = start_ingest_run(
            init_result.app_path,
            kind=f"overseas_minute:{interval_minutes}m",
            market=resolved_market,
            symbol=normalized_symbol,
        )

    try:
        bars = call_with_sdk_client(
            lambda client: _fetch_overseas_minutes_async(
                client,
                market=resolved_market,
                symbol=normalized_symbol,
                start=start,
                interval_minutes=interval_minutes,
                count=count,
                include_previous=include_previous,
            ),
            profile=profile,
            config_path=config_path,
        )
        stored = 0
        if init_result:
            values = [minute_bar_to_db_values(bar) for bar in bars]
            with connect(init_result.path) as connection:
                stored = insert_overseas_minute_bars(connection, values)
            finish_ingest_run(
                init_result.app_path,
                run_id,
                status="success",
                rows_written=stored,
            )
            record_api_log(
                init_result.app_path,
                endpoint=f"overseas_minute:{resolved_market}:{interval_minutes}m",
                status_code=200,
            )
    except Exception as exc:
        if init_result and run_id is not None:
            message = str(exc)
            finish_ingest_run(
                init_result.app_path,
                run_id,
                status="failed",
                error=message,
            )
            record_api_log(
                init_result.app_path,
                endpoint=f"overseas_minute:{resolved_market}:{interval_minutes}m",
                error=message,
            )
        raise

    return OverseasMinuteResult(
        db_path=initialized_path,
        market=bars[0].market if bars else resolved_market,
        symbol=bars[0].symbol if bars else normalized_symbol,
        interval_minutes=interval_minutes,
        fetched=len(bars),
        stored=stored,
        bars=bars,
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


def normalize_period(period: str) -> str:
    normalized = period.strip().upper()
    if normalized not in {"D", "W", "M", "Y"}:
        raise ValueError("period must be one of: D, W, M, Y")
    return normalized


async def _fetch_ohlcv_history_async(
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
    normalized_period = normalize_period(period)
    if parse_date(start) > parse_date(end):
        raise ValueError("start must be on or before end")
    if market in {"KOSPI", "KOSDAQ"}:
        method = {
            "D": client.domestic.chart.daily,
            "W": client.domestic.chart.weekly,
            "M": client.domestic.chart.monthly,
            "Y": client.domestic.chart.yearly,
        }[normalized_period]
        return await method(
            symbol,
            start=start,
            end=end,
            market=market,
            adjusted=adjusted,
            max_pages=max_pages,
        )
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


async def _fetch_overseas_minutes_async(
    client: KisClient,
    *,
    market: str,
    symbol: str,
    start: str,
    interval_minutes: int,
    count: int,
    include_previous: bool,
) -> list[OverseasMinuteBar]:
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


def _normalize_store(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"duckdb", "supabase"}:
        raise ValueError("store must be one of: duckdb, supabase")
    return normalized
