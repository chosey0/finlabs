from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.panel import Panel
from rich.table import Table

from kis_cli.cli.common import console, result_table
from kis_cli.storage.app_db import default_app_database_file
from kis_cli.storage.app_repositories import IngestRunRecord, find_api_logs, find_ingest_runs

logs_app = typer.Typer(help="Inspect local app logs.", no_args_is_help=True)

INGEST_RUN_FIELDS = [
    "id",
    "kind",
    "market",
    "symbol",
    "started_at",
    "finished_at",
    "status",
    "rows_written",
    "error",
]
API_LOG_FIELDS = ["endpoint", "tr_id", "status_code", "requested_at", "elapsed_ms", "error"]


@logs_app.command("runs")
def logs_runs(
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=500, help="Maximum number of runs to show."),
    ] = 20,
    status: Annotated[
        str | None,
        typer.Option("--status", help="Filter by run status, for example success or failed."),
    ] = None,
    kind: Annotated[
        str | None,
        typer.Option("--kind", help="Filter by run kind, for example symbols or ohlcv:1d."),
    ] = None,
    market: Annotated[
        str | None,
        typer.Option("--market", help="Filter by market, for example KOSPI or NASDAQ."),
    ] = None,
    symbol: Annotated[
        str | None,
        typer.Option("--symbol", help="Filter by symbol, for example 005930 or AAPL."),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Filter rows at or after this KST ISO timestamp/date."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table, json, or csv."),
    ] = "table",
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Inspect a custom app SQLite database path."),
    ] = None,
) -> None:
    """Show recent ingest run records from the app database."""
    normalized_format = _normalize_output_format(output_format)
    try:
        app_db_path = _resolve_existing_app_db_path(path)
        if normalized_format == "table":
            with console.status("Loading ingest runs..."):
                rows = find_ingest_runs(
                    app_db_path,
                    limit=limit,
                    status=status,
                    kind=kind,
                    market=market,
                    symbol=symbol,
                    since=since,
                )
        else:
            rows = find_ingest_runs(
                app_db_path,
                limit=limit,
                status=status,
                kind=kind,
                market=market,
                symbol=symbol,
                since=since,
            )
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_ingest_runs(rows, app_db_path, output_format=normalized_format)


@logs_app.command("api")
def logs_api(
    limit: Annotated[
        int,
        typer.Option("--limit", min=1, max=500, help="Maximum number of API log rows to show."),
    ] = 20,
    endpoint: Annotated[
        str | None,
        typer.Option("--endpoint", help="Filter by endpoint substring."),
    ] = None,
    since: Annotated[
        str | None,
        typer.Option("--since", help="Filter rows at or after this KST ISO timestamp/date."),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--format", help="Output format: table, json, or csv."),
    ] = "table",
    path: Annotated[
        Path | None,
        typer.Option("--path", help="Inspect a custom app SQLite database path."),
    ] = None,
) -> None:
    """Show recent API log records from the app database."""
    normalized_format = _normalize_output_format(output_format)
    try:
        app_db_path = _resolve_existing_app_db_path(path)
        if normalized_format == "table":
            with console.status("Loading API logs..."):
                rows = find_api_logs(
                    app_db_path,
                    limit=limit,
                    endpoint=endpoint,
                    since=since,
                )
        else:
            rows = find_api_logs(
                app_db_path,
                limit=limit,
                endpoint=endpoint,
                since=since,
            )
    except FileNotFoundError as exc:
        raise typer.BadParameter(str(exc)) from exc
    _print_api_logs(rows, app_db_path, output_format=normalized_format)


def _print_ingest_runs(
    rows: list[IngestRunRecord],
    app_db_path: Path,
    *,
    output_format: str,
) -> None:
    serialized = [_ingest_run_to_dict(row) for row in rows]
    if output_format == "json":
        typer.echo(json.dumps(serialized, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        _write_dict_csv(serialized, sys.stdout, INGEST_RUN_FIELDS)
        return

    summary = result_table()
    summary.add_row("App database", str(app_db_path))
    summary.add_row("Rows", str(len(rows)))
    console.print(Panel(summary, title="Ingest runs", border_style="green", box=box.ROUNDED))

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("ID", justify="right")
    table.add_column("Kind", style="bold cyan", no_wrap=True)
    table.add_column("Market")
    table.add_column("Symbol")
    table.add_column("Status")
    table.add_column("Rows", justify="right")
    table.add_column("Started at")
    table.add_column("Finished at")
    table.add_column("Error")
    for row in rows:
        table.add_row(
            str(row.id),
            row.kind,
            row.market or "",
            row.symbol or "",
            row.status,
            str(row.rows_written),
            row.started_at,
            row.finished_at or "",
            row.error or "",
        )
    console.print(table)


def _print_api_logs(
    rows: list[dict[str, object]],
    app_db_path: Path,
    *,
    output_format: str,
) -> None:
    if output_format == "json":
        typer.echo(json.dumps(rows, ensure_ascii=False, indent=2))
        return
    if output_format == "csv":
        _write_dict_csv(rows, sys.stdout, API_LOG_FIELDS)
        return

    summary = result_table()
    summary.add_row("App database", str(app_db_path))
    summary.add_row("Rows", str(len(rows)))
    console.print(Panel(summary, title="API logs", border_style="green", box=box.ROUNDED))

    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Endpoint", style="bold cyan", no_wrap=True)
    table.add_column("TR ID", no_wrap=True)
    table.add_column("Status", justify="right")
    table.add_column("Requested at")
    table.add_column("Elapsed ms", justify="right")
    table.add_column("Error")
    for row in rows:
        table.add_row(
            str(row["endpoint"]),
            str(row["tr_id"] or ""),
            "" if row["status_code"] is None else str(row["status_code"]),
            str(row["requested_at"]),
            "" if row["elapsed_ms"] is None else str(row["elapsed_ms"]),
            str(row["error"] or ""),
        )
    console.print(table)


def _normalize_output_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"table", "json", "csv"}:
        raise typer.BadParameter("format must be one of: table, json, csv")
    return normalized


def _write_dict_csv(rows, file, fieldnames: list[str]) -> None:
    writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def _ingest_run_to_dict(row: IngestRunRecord) -> dict[str, object]:
    return {
        "id": row.id,
        "kind": row.kind,
        "market": row.market,
        "symbol": row.symbol,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "status": row.status,
        "rows_written": row.rows_written,
        "error": row.error,
    }


def _resolve_existing_app_db_path(path: Path | None) -> Path:
    app_db_path = (path or default_app_database_file()).expanduser()
    if not app_db_path.exists():
        raise FileNotFoundError(
            f"app database not found at {app_db_path}; run 'kiscli db init' first"
        )
    return app_db_path
