from __future__ import annotations

import sqlite3
from pathlib import Path

from kis_cli.config.paths import data_dir

APP_TABLE_NAMES = ("api_logs", "ingest_runs")


def default_app_database_file() -> Path:
    return data_dir() / "app.db"


def connect_app(path: Path | None = None) -> sqlite3.Connection:
    db_path = (path or default_app_database_file()).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_app_database(path: Path | None = None) -> Path:
    db_path = (path or default_app_database_file()).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect_app(db_path) as connection:
        connection.executescript(
            """
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
            """
        )
    return db_path
