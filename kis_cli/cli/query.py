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
    console,
    export_format,
    export_ohlcv_rows,
    normalize_output_format,
    result_table,
    write_ohlcv_csv,
)
from kis_cli.services.query import OhlcvQueryResult, query_stored_daily_ohlcv

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
            with console.status("Querying stored OHLCV rows..."):
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
        )
        return

    _print_ohlcv_query_result(result, output_format=normalized_format)


def _print_ohlcv_query_result(result: OhlcvQueryResult, *, output_format: str) -> None:
    if output_format == "json":
        typer.echo(json.dumps(result.rows, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        write_ohlcv_csv(result.rows, sys.stdout)
        return

    if not result.rows:
        console.print("No OHLCV bars found")
        return

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Market", style="bold cyan")
    table.add_column("Symbol", style="bold")
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
    console.print(table)


def _print_export_result(*, export_path: Path, row_count: int, export_format: str) -> None:
    table = result_table()
    table.add_row("Path", str(export_path.expanduser()))
    table.add_row("Format", export_format)
    table.add_row("Rows", str(row_count))
    console.print(Panel(table, title="OHLCV exported", border_style="green", box=box.ROUNDED))


def _format_optional(value: object) -> str:
    return "" if value is None else str(value)
