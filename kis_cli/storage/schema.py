from __future__ import annotations

import sqlite3

TABLE_NAMES = ("symbols", "ohlcv_bars", "realtime_ticks", "api_logs", "ingest_runs")


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            standard_code TEXT,
            realtime_symbol TEXT,
            korean_name TEXT,
            english_name TEXT,
            security_type TEXT,
            currency TEXT,
            exchange_id TEXT,
            exchange_code TEXT,
            exchange_name TEXT,
            country_code TEXT,
            listed_date TEXT,
            base_price INTEGER,
            lot_size INTEGER,
            raw_source TEXT NOT NULL DEFAULT '',
            raw TEXT NOT NULL DEFAULT '{}',
            downloaded_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (market, symbol)
        );

        CREATE TABLE IF NOT EXISTS ohlcv_bars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            interval TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            open REAL NOT NULL,
            high REAL NOT NULL,
            low REAL NOT NULL,
            close REAL NOT NULL,
            volume INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (market, symbol, interval, timestamp)
        );

        CREATE TABLE IF NOT EXISTS realtime_ticks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            market TEXT NOT NULL,
            symbol TEXT NOT NULL,
            exchange_ts TEXT NOT NULL,
            received_at TEXT NOT NULL,
            received_seq INTEGER NOT NULL,
            seq INTEGER NOT NULL,
            price REAL NOT NULL,
            volume INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (market, symbol, exchange_ts, seq)
        );

        CREATE TABLE IF NOT EXISTS api_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT NOT NULL,
            tr_id TEXT,
            status_code INTEGER,
            requested_at TEXT NOT NULL,
            elapsed_ms INTEGER,
            error TEXT
        );

        CREATE TABLE IF NOT EXISTS ingest_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            market TEXT,
            symbol TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            rows_written INTEGER NOT NULL DEFAULT 0,
            error TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_symbols_market_name
            ON symbols (market, korean_name, english_name);
        CREATE INDEX IF NOT EXISTS idx_ohlcv_lookup
            ON ohlcv_bars (market, symbol, interval, timestamp);
        CREATE INDEX IF NOT EXISTS idx_realtime_order
            ON realtime_ticks (market, symbol, exchange_ts, seq, received_seq);
        """
    )
