from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel

from kis import KisApiError, KisAuthError

from kis_cli.cli.common import console, prompt_supabase_dsn_if_missing, result_table
from kis_cli.services.chart import (
    ChartHistoryResult,
    OverseasMinuteResult,
    collect_ohlcv_history,
    collect_overseas_minutes,
)

chart_app = typer.Typer(help="Collect REST OHLCV history.", no_args_is_help=True)


@chart_app.command("history")
def chart_history(
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Stock symbol to collect, for example 005930 or AAPL."),
    ],
    start: Annotated[
        str,
        typer.Option("--start", help="Start date in YYYY-MM-DD or YYYYMMDD format."),
    ],
    end: Annotated[
        str | None,
        typer.Option("--end", help="End date in YYYY-MM-DD or YYYYMMDD format. Defaults to today."),
    ] = None,
    period: Annotated[
        str,
        typer.Option("--period", help="Period: D, W, M, or Y."),
    ] = "D",
    profile: Annotated[
        str | None,
        typer.Option("--profile", help="Profile name to authenticate. Defaults to active_profile."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Read config from a custom path."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
    save: Annotated[
        bool,
        typer.Option("--save", help="Persist bars into the selected ohlcv_bars table."),
    ] = False,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend to write when --save is used: duckdb or supabase."),
    ] = "duckdb",
    adjusted: Annotated[
        bool,
        typer.Option("--adjusted/--raw-price", help="Use adjusted prices for domestic history."),
    ] = True,
    max_pages: Annotated[
        int,
        typer.Option("--max-pages", min=1, max=1000, help="Maximum continuation requests."),
    ] = 100,
) -> None:
    """Collect domestic or overseas OHLCV history with continuation support."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period=period,
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        store=store,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("daily")
def chart_daily(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend to write when --save is used: duckdb or supabase."),
    ] = "duckdb",
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect daily OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="D",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        store=store,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("weekly")
def chart_weekly(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend to write when --save is used: duckdb or supabase."),
    ] = "duckdb",
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect weekly OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="W",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        store=store,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("monthly")
def chart_monthly(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend to write when --save is used: duckdb or supabase."),
    ] = "duckdb",
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect monthly OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="M",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        store=store,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("yearly")
def chart_yearly(
    symbol: Annotated[str, typer.Option("--symbol", help="Stock symbol to collect.")],
    start: Annotated[str, typer.Option("--start", help="Start date.")],
    end: Annotated[str | None, typer.Option("--end", help="End date. Defaults to today.")] = None,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    store: Annotated[
        str,
        typer.Option("--store", help="Storage backend to write when --save is used: duckdb or supabase."),
    ] = "duckdb",
    adjusted: Annotated[bool, typer.Option("--adjusted/--raw-price")] = True,
    max_pages: Annotated[int, typer.Option("--max-pages", min=1, max=1000)] = 100,
) -> None:
    """Collect yearly OHLCV history."""
    _run_chart_history(
        symbol=symbol,
        start=start,
        end=end,
        period="Y",
        profile=profile,
        path=path,
        db_path=db_path,
        save=save,
        store=store,
        adjusted=adjusted,
        max_pages=max_pages,
    )


@chart_app.command("minutes")
def chart_minutes(
    symbol: Annotated[str, typer.Option("--symbol", help="Overseas stock symbol to collect.")],
    start: Annotated[
        str,
        typer.Option("--start", help="Start local exchange datetime, for example '2024-10-14 14:01:00'."),
    ],
    interval_minutes: Annotated[
        int,
        typer.Option("--interval-minutes", min=1, help="Minute interval, for example 1 or 5."),
    ] = 1,
    count: Annotated[
        int,
        typer.Option("--count", min=1, max=120, help="Records per request. KIS maximum is 120."),
    ] = 120,
    profile: Annotated[str | None, typer.Option("--profile")] = None,
    path: Annotated[Path | None, typer.Option("--path")] = None,
    db_path: Annotated[Path | None, typer.Option("--db-path")] = None,
    save: Annotated[bool, typer.Option("--save")] = False,
    include_previous: Annotated[
        bool,
        typer.Option("--include-previous/--today-only", help="Include previous trading day for continuation."),
    ] = True,
) -> None:
    """Collect overseas stock minute bars."""
    try:
        with console.status("Collecting overseas minute bars..."):
            result = collect_overseas_minutes(
                symbol=symbol,
                start=start,
                interval_minutes=interval_minutes,
                count=count,
                profile=profile,
                config_path=path,
                db_path=db_path,
                save=save,
                include_previous=include_previous,
            )
    except (FileNotFoundError, ValueError, KisAuthError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_overseas_minute_result(result)


def _run_chart_history(
    *,
    symbol: str,
    start: str,
    end: str | None,
    period: str,
    profile: str | None,
    path: Path | None,
    db_path: Path | None,
    save: bool,
    store: str,
    adjusted: bool,
    max_pages: int,
) -> None:
    normalized_store = _normalize_store(store)
    if save and normalized_store == "supabase" and db_path is not None:
        raise typer.BadParameter("--db-path is only valid with --store duckdb")
    supabase_dsn = prompt_supabase_dsn_if_missing() if save and normalized_store == "supabase" else None
    try:
        with console.status("Collecting OHLCV history..."):
            result = collect_ohlcv_history(
                symbol=symbol,
                start=start,
                end=end,
                period=period,
                profile=profile,
                config_path=path,
                db_path=db_path,
                save=save,
                store=normalized_store,
                supabase_dsn=supabase_dsn,
                adjusted=adjusted,
                max_pages=max_pages,
            )
    except (FileNotFoundError, ValueError, KisAuthError, KisApiError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    _print_chart_history_result(result)


def _print_chart_history_result(result: ChartHistoryResult) -> None:
    table = result_table()
    table.add_row("Market", result.market)
    table.add_row("Symbol", result.symbol)
    table.add_row("Interval", result.interval)
    table.add_row("Fetched", str(result.fetched))
    table.add_row("Stored", str(result.stored))
    table.add_row("Store", result.store)
    table.add_row("Database", str(result.db_path) if result.db_path else "-")
    if result.bars:
        table.add_row("First", result.bars[0].timestamp)
        table.add_row("Last", result.bars[-1].timestamp)
    console.print(Panel(table, title="OHLCV history", border_style="green", box=box.ROUNDED))


def _print_overseas_minute_result(result: OverseasMinuteResult) -> None:
    table = result_table()
    table.add_row("Market", result.market)
    table.add_row("Symbol", result.symbol)
    table.add_row("Interval", f"{result.interval_minutes}m")
    table.add_row("Fetched", str(result.fetched))
    table.add_row("Stored", str(result.stored))
    table.add_row("Database", str(result.db_path) if result.db_path else "-")
    if result.bars:
        table.add_row("First local", f"{result.bars[0].local_date} {result.bars[0].local_time}")
        table.add_row("Last local", f"{result.bars[-1].local_date} {result.bars[-1].local_time}")
    console.print(
        Panel(
            table,
            title="Overseas minute bars",
            border_style="green",
            box=box.ROUNDED,
        )
    )


def _normalize_store(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"duckdb", "supabase"}:
        raise typer.BadParameter("store must be one of: duckdb, supabase")
    return normalized
