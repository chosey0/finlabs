from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from kis_cli.cli.common import (
    MARKET_STYLE,
    SYMBOL_STYLE,
    TABLE_HEADER_STYLE,
    cli_console,
    export_format,
    export_ohlcv_rows,
    export_overseas_minute_rows,
    normalize_output_format,
    result_table,
    write_ohlcv_csv,
    write_overseas_minute_csv,
)
from kis_cli.services.query import (
    CandleSymbolQueryResult,
    OhlcvQueryResult,
    OverseasMinuteQueryResult,
    query_stored_candle_symbols,
    query_stored_daily_ohlcv,
    query_stored_overseas_minutes,
)

query_app = typer.Typer(help="Query and export locally stored data.", no_args_is_help=True)


@query_app.command("ohlcv")
def query_ohlcv(
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Stock symbol to query, for example 005930 or AAPL."),
    ],
    start: Annotated[
        str | None,
        typer.Option("--start", help="Start date in YYYY-MM-DD or YYYYMMDD format."),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option("--end", help="End date in YYYY-MM-DD or YYYYMMDD format."),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=10000, help="Maximum number of daily bars to show."),
    ] = 20,
    all_rows: Annotated[
        bool,
        typer.Option("--all", help="Show all matching daily bars instead of applying --limit."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table, json, or csv."),
    ] = "table",
    export_path: Annotated[
        Path | None,
        typer.Option("--export", help="Export rows to a .csv or .json file."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
) -> None:
    """Query locally stored daily OHLCV bars."""
    normalized_format = normalize_output_format(output_format)
    try:
        if normalized_format == "table" or export_path is not None:
            with cli_console().status("Querying stored OHLCV rows..."):
                result = query_stored_daily_ohlcv(
                    symbol=symbol,
                    start=start,
                    end=end,
                    limit=None if all_rows else limit,
                    db_path=db_path,
                )
        else:
            result = query_stored_daily_ohlcv(
                symbol=symbol,
                start=start,
                end=end,
                limit=None if all_rows else limit,
                db_path=db_path,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if export_path is not None:
        selected_format = export_format(export_path, fallback=normalized_format)
        export_ohlcv_rows(result.rows, export_path, selected_format)
        _print_export_result(
            export_path=export_path,
            row_count=len(result.rows),
            export_format=selected_format,
            title="OHLCV exported",
        )
        return

    _print_ohlcv_query_result(result, output_format=normalized_format)


@query_app.command("minutes")
def query_minutes(
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Stock symbol to query, for example AAPL."),
    ],
    interval_minutes: Annotated[
        int | None,
        typer.Option("--interval-minutes", help="Filter by bar interval in minutes."),
    ] = None,
    start: Annotated[
        str | None,
        typer.Option(
            "--start",
            help="Start boundary: YYYY-MM-DD, YYYYMMDD, or YYYY-MM-DD HH:MM:SS (local bar time).",
        ),
    ] = None,
    end: Annotated[
        str | None,
        typer.Option(
            "--end",
            help="End boundary: YYYY-MM-DD, YYYYMMDD, or YYYY-MM-DD HH:MM:SS (local bar time).",
        ),
    ] = None,
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=10000, help="Maximum number of minute bars to show."),
    ] = 20,
    all_rows: Annotated[
        bool,
        typer.Option("--all", help="Show all matching minute bars instead of applying --limit."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table, json, or csv."),
    ] = "table",
    export_path: Annotated[
        Path | None,
        typer.Option("--export", help="Export rows to a .csv or .json file."),
    ] = None,
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
) -> None:
    """Query locally stored overseas minute bars (overseas_minute_bars)."""
    normalized_format = normalize_output_format(output_format)
    try:
        if normalized_format == "table" or export_path is not None:
            with cli_console().status("Querying stored overseas minute bars..."):
                result = query_stored_overseas_minutes(
                    symbol=symbol,
                    interval_minutes=interval_minutes,
                    start=start,
                    end=end,
                    limit=None if all_rows else limit,
                    db_path=db_path,
                )
        else:
            result = query_stored_overseas_minutes(
                symbol=symbol,
                interval_minutes=interval_minutes,
                start=start,
                end=end,
                limit=None if all_rows else limit,
                db_path=db_path,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if export_path is not None:
        selected_format = export_format(export_path, fallback=normalized_format)
        export_overseas_minute_rows(result.rows, export_path, selected_format)
        _print_export_result(
            export_path=export_path,
            row_count=len(result.rows),
            export_format=selected_format,
            title="Overseas minute bars exported",
        )
        return

    _print_minutes_query_result(result, output_format=normalized_format)


@query_app.command("candle-symbols")
def query_candle_symbols(
    source: Annotated[
        str,
        typer.Option("--source", help="Candle table source: all, ohlcv, or minutes."),
    ] = "all",
    market: Annotated[
        str | None,
        typer.Option("--market", help="Restrict results to one market, for example NASDAQ."),
    ] = None,
    interval: Annotated[
        str | None,
        typer.Option("--interval", help="Restrict interval, for example 1d or 1m."),
    ] = None,
    symbols_only: Annotated[
        bool,
        typer.Option("--symbols-only", help="Print only distinct symbols separated by spaces."),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table, json, or csv."),
    ] = "table",
    db_path: Annotated[
        Path | None,
        typer.Option("--db-path", help="Use a custom DuckDB warehouse path."),
    ] = None,
) -> None:
    """List symbols that have actual stored candle rows."""
    normalized_format = normalize_output_format(output_format)
    try:
        with cli_console().status("Querying symbols with stored candle rows..."):
            result = query_stored_candle_symbols(
                source=source,
                market=market,
                interval=interval,
                db_path=db_path,
            )
    except (FileNotFoundError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc

    if symbols_only:
        typer.echo(" ".join(result.symbols))
        return

    _print_candle_symbol_query_result(result, output_format=normalized_format)


def _print_ohlcv_query_result(result: OhlcvQueryResult, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.rows, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        write_ohlcv_csv(result.rows, sys.stdout)
        return

    if not result.rows:
        cli_console().print("No OHLCV bars found")
        return

    table = Table(box=box.SIMPLE_HEAVY, header_style=TABLE_HEADER_STYLE)
    table.add_column("Market", style=MARKET_STYLE)
    table.add_column("Symbol", style=SYMBOL_STYLE)
    table.add_column("Date")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Change Rate", justify="right")
    table.add_column("Amount", justify="right")
    for row in result.rows:
        table.add_row(
            str(row["market"]),
            str(row["symbol"]),
            str(row["timestamp"]),
            str(row["open"]),
            str(row["high"]),
            str(row["low"]),
            str(row["close"]),
            str(row["volume"]),
            _format_optional(row.get("change")),
            _format_optional(row.get("change_rate")),
            _format_optional(row.get("amount")),
        )
    cli_console().print(table)


def _print_minutes_query_result(result: OverseasMinuteQueryResult, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.rows, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        write_overseas_minute_csv(result.rows, sys.stdout)
        return

    if not result.rows:
        cli_console().print("No overseas minute bars found")
        return

    table = Table(box=box.SIMPLE_HEAVY, header_style=TABLE_HEADER_STYLE)
    table.add_column("Market", style=MARKET_STYLE)
    table.add_column("Symbol", style=SYMBOL_STYLE)
    table.add_column("Int(m)", justify="right")
    table.add_column("Local date")
    table.add_column("Local time")
    table.add_column("Open", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Low", justify="right")
    table.add_column("Close", justify="right")
    table.add_column("Volume", justify="right")
    table.add_column("Amount", justify="right")
    for row in result.rows:
        table.add_row(
            str(row["market"]),
            str(row["symbol"]),
            str(row["interval_minutes"]),
            str(row["local_date"]),
            str(row["local_time"]),
            str(row["open"]),
            str(row["high"]),
            str(row["low"]),
            str(row["close"]),
            str(row["volume"]),
            _format_optional(row.get("amount")),
        )
    cli_console().print(table)


def _print_candle_symbol_query_result(result: CandleSymbolQueryResult, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.rows, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        _write_candle_symbol_csv(result.rows, sys.stdout)
        return

    if not result.rows:
        cli_console().print("No symbols with stored candle rows found")
        return

    table = Table(box=box.SIMPLE_HEAVY, header_style=TABLE_HEADER_STYLE)
    table.add_column("Source")
    table.add_column("Market", style=MARKET_STYLE)
    table.add_column("Symbol", style=SYMBOL_STYLE)
    table.add_column("Interval")
    table.add_column("Bars", justify="right")
    table.add_column("First")
    table.add_column("Last")
    for row in result.rows:
        table.add_row(
            str(row["source"]),
            str(row["market"]),
            str(row["symbol"]),
            str(row["interval"]),
            str(row["bar_count"]),
            str(row["first_timestamp"]),
            str(row["last_timestamp"]),
        )
    cli_console().print(table)


def _write_candle_symbol_csv(rows, output) -> None:
    import csv

    fieldnames = ["source", "market", "symbol", "interval", "bar_count", "first_timestamp", "last_timestamp"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def _print_export_result(
    *,
    export_path: Path,
    row_count: int,
    export_format: str,
    title: str = "OHLCV exported",
) -> None:
    table = result_table()
    table.add_row("Path", str(export_path.expanduser()))
    table.add_row("Format", export_format)
    table.add_row("Rows", str(row_count))
    cli_console().print(Panel(table, title=title, border_style="green", box=box.ROUNDED))


def _format_optional(value: object) -> str:
    return "" if value is None else str(value)
