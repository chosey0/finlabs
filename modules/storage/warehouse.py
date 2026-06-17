"""Warehouse path helpers shared by read-side tools."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_data_dir


APP_NAME = "finlabs"
APP_AUTHOR = "finlabs"


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def default_warehouse_file() -> Path:
    return data_dir() / "warehouse.duckdb"
