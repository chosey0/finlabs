from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel

from kis_cli.cli.common import console, result_table
from kis_cli.core.auth import KisAuthError
from kis_cli.core.client import KisApiError
from kis_cli.services.chart import ChartHistoryResult, collect_ohlcv_history

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
        typer.Option("--save", help="Persist bars into the local warehouse ohlcv_bars table."),
    ] = False,
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
        adjusted=adjusted,
        max_pages=max_pages,
    )


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
    adjusted: bool,
    max_pages: int,
) -> None:
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
    table.add_row("Database", str(result.db_path) if result.db_path else "-")
    if result.bars:
        table.add_row("First", result.bars[0].timestamp)
        table.add_row("Last", result.bars[-1].timestamp)
    console.print(Panel(table, title="OHLCV history", border_style="green", box=box.ROUNDED))
