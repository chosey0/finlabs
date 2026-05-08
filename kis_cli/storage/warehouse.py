from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from kis_cli.config.paths import data_dir

WAREHOUSE_TABLE_NAMES = ("symbols", "ohlcv_bars", "realtime_ticks")


@dataclass(frozen=True)
class WarehouseInitResult:
    path: Path
    tables: tuple[str, ...]


def default_warehouse_file() -> Path:
    return data_dir() / "warehouse.duckdb"


def connect_warehouse(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    db_path = (path or default_warehouse_file()).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_warehouse(path: Path | None = None) -> WarehouseInitResult:
    db_path = (path or default_warehouse_file()).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_warehouse(db_path) as connection:
        create_warehouse_schema(connection)
    return WarehouseInitResult(path=db_path, tables=WAREHOUSE_TABLE_NAMES)


def create_warehouse_schema(connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS symbols (
            market VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            standard_code VARCHAR,
            realtime_symbol VARCHAR,
            korean_name VARCHAR,
            english_name VARCHAR,
            security_type VARCHAR,
            currency VARCHAR,
            exchange_id VARCHAR,
            exchange_code VARCHAR,
            exchange_name VARCHAR,
            country_code VARCHAR,
            listed_date VARCHAR,
            base_price BIGINT,
            lot_size BIGINT,
            raw_source VARCHAR NOT NULL DEFAULT '',
            raw JSON NOT NULL DEFAULT '{}',
            downloaded_at VARCHAR NOT NULL DEFAULT '',
            created_at VARCHAR NOT NULL DEFAULT '',
            updated_at VARCHAR NOT NULL DEFAULT '',
            UNIQUE (market, symbol)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ohlcv_bars (
            market VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            interval VARCHAR NOT NULL,
            timestamp VARCHAR NOT NULL,
            open DOUBLE NOT NULL,
            high DOUBLE NOT NULL,
            low DOUBLE NOT NULL,
            close DOUBLE NOT NULL,
            volume BIGINT NOT NULL,
            change DOUBLE,
            change_rate DOUBLE,
            amount DOUBLE,
            created_at VARCHAR NOT NULL DEFAULT '',
            UNIQUE (market, symbol, interval, timestamp)
        )
        """
    )
    connection.execute("ALTER TABLE ohlcv_bars ADD COLUMN IF NOT EXISTS change DOUBLE")
    connection.execute("ALTER TABLE ohlcv_bars ADD COLUMN IF NOT EXISTS change_rate DOUBLE")
    connection.execute("ALTER TABLE ohlcv_bars ADD COLUMN IF NOT EXISTS amount DOUBLE")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS realtime_ticks (
            market VARCHAR NOT NULL,
            symbol VARCHAR NOT NULL,
            exchange_ts VARCHAR NOT NULL,
            received_at VARCHAR NOT NULL,
            received_seq BIGINT NOT NULL,
            seq BIGINT NOT NULL,
            price DOUBLE NOT NULL,
            volume BIGINT NOT NULL,
            created_at VARCHAR NOT NULL DEFAULT '',
            UNIQUE (market, symbol, exchange_ts, seq)
        )
        """
    )
