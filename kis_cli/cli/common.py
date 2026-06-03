from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from kis_cli.config.paths import default_config_file
from kis_cli.config.profiles import ENV_FILE_NAME, upsert_env_value
from kis_cli.config.resolver import read_env_file
from kis_cli.storage import SUPABASE_DSN_ENV


def _rich_console_width() -> int | None:
    raw = os.environ.get("COLUMNS", "").strip()
    if not raw:
        return None
    try:
        width = int(raw)
    except ValueError:
        return None
    return width if width > 0 else None


def _rich_console_height() -> int | None:
    raw = os.environ.get("LINES", "").strip()
    if not raw:
        return None
    try:
        height = int(raw)
    except ValueError:
        return None
    return height if height > 0 else None


def cli_console() -> Console:
    """Rich console for CLI output; honors COLUMNS/LINES at call time.

    Rich only fixes dimensions when *both* width and height are set; otherwise
    it falls back to the detected terminal size (often 80 columns under pytest).
    """
    width = _rich_console_width()
    if width is None:
        return Console()
    height = _rich_console_height() or 25
    return Console(width=width, height=height)


console = Console()
CANCEL_EXIT_CODE = 130
TABLE_HEADER_STYLE = "bold white on blue"
FIELD_STYLE = "bold blue"
MARKET_STYLE = "bold blue"
SYMBOL_STYLE = "bold magenta"


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


def export_overseas_minute_rows(rows: list[dict[str, object]], path: Path, export_format: str) -> None:
    export_path = path.expanduser()
    export_path.parent.mkdir(parents=True, exist_ok=True)
    if export_format == "json":
        export_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    with export_path.open("w", encoding="utf-8", newline="") as file:
        write_overseas_minute_csv(rows, file)


def write_overseas_minute_csv(rows, file) -> None:
    fieldnames = [
        "market",
        "symbol",
        "interval_minutes",
        "local_business_date",
        "local_date",
        "local_time",
        "korea_date",
        "korea_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
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
    table.add_column("Field", style=FIELD_STYLE, no_wrap=True)
    table.add_column("Value", overflow="fold")
    return table


def prompt_supabase_dsn_if_missing() -> str | None:
    if os.environ.get(SUPABASE_DSN_ENV):
        return None
    env_path = default_config_file().parent / ENV_FILE_NAME
    env_values = read_env_file(env_path)
    if env_values.get(SUPABASE_DSN_ENV):
        os.environ[SUPABASE_DSN_ENV] = env_values[SUPABASE_DSN_ENV]
        return None
    dsn = typer.prompt(
        f"{SUPABASE_DSN_ENV} is not set. Supabase PostgreSQL DSN",
        hide_input=True,
    )
    if not dsn.strip():
        raise typer.BadParameter("Supabase PostgreSQL DSN must not be empty")
    cleaned = dsn.strip()
    upsert_env_value(env_path, SUPABASE_DSN_ENV, cleaned)
    return cleaned
