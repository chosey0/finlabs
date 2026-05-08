from __future__ import annotations

import csv
import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

console = Console()
CANCEL_EXIT_CODE = 130


def normalize_output_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"table", "json", "csv"}:
        raise typer.BadParameter("format must be one of: table, json, csv")
    return normalized


def export_format(path: Path, *, fallback: str) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".json":
        return "json"
    if fallback in {"csv", "json"}:
        return fallback
    raise typer.BadParameter("export path must end with .csv or .json, or pass --format csv|json")


def export_ohlcv_rows(rows: list[dict[str, object]], path: Path, export_format: str) -> None:
    export_path = path.expanduser()
    export_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "json":
        export_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    with export_path.open("w", encoding="utf-8", newline="") as file:
        write_ohlcv_csv(rows, file)


def write_ohlcv_csv(rows, file) -> None:
    fieldnames = [
        "market",
        "symbol",
        "interval",
        "timestamp",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "change",
        "change_rate",
        "amount",
    ]
    writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)


def format_decimal(value) -> str:
    if value is None:
        return "-"
    return format(value, "f")


def result_table() -> Table:
    table = Table.grid(padding=(0, 2))
    table.add_column("Field", style="bold cyan", no_wrap=True)
    table.add_column("Value", overflow="fold")
    return table
