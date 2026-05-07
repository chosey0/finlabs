from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from kis_cli.config.paths import data_dir
from kis_cli.storage.schema import TABLE_NAMES, create_schema


@dataclass(frozen=True)
class DatabaseInitResult:
    path: Path
    tables: tuple[str, ...]


@dataclass(frozen=True)
class TableColumn:
    cid: int
    name: str
    type: str
    not_null: bool
    default: str | None
    primary_key: bool


@dataclass(frozen=True)
class TableIndex:
    name: str
    unique: bool
    origin: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class DatabaseTable:
    name: str
    columns: tuple[TableColumn, ...]
    indexes: tuple[TableIndex, ...]


@dataclass(frozen=True)
class DatabaseSchemaResult:
    path: Path
    tables: tuple[DatabaseTable, ...]


@dataclass(frozen=True)
class TableCount:
    name: str
    rows: int


@dataclass(frozen=True)
class DatabaseCountsResult:
    path: Path
    tables: tuple[TableCount, ...]
    total_rows: int


def default_database_file() -> Path:
    return data_dir() / "kis-cli.db"


def connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = (path or default_database_file()).expanduser()
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database(path: Path | None = None) -> DatabaseInitResult:
    db_path = (path or default_database_file()).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as connection:
        create_schema(connection)
    return DatabaseInitResult(path=db_path, tables=TABLE_NAMES)


def inspect_database_schema(path: Path | None = None) -> DatabaseSchemaResult:
    db_path = (path or default_database_file()).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"database not found at {db_path}; run 'kiscli db init' first")

    with connect(db_path) as connection:
        table_names = _table_names(connection)
        tables = tuple(_inspect_table(connection, table_name) for table_name in table_names)
    return DatabaseSchemaResult(path=db_path, tables=tables)


def inspect_database_counts(path: Path | None = None) -> DatabaseCountsResult:
    db_path = (path or default_database_file()).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"database not found at {db_path}; run 'kiscli db init' first")

    with connect(db_path) as connection:
        tables = tuple(
            TableCount(
                name=table_name,
                rows=connection.execute(
                    f"SELECT COUNT(*) AS count FROM {_quote_identifier(table_name)}"
                ).fetchone()["count"],
            )
            for table_name in _table_names(connection)
        )
    return DatabaseCountsResult(
        path=db_path,
        tables=tables,
        total_rows=sum(table.rows for table in tables),
    )


def _table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        row["name"]
        for row in connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
    ]


def _inspect_table(connection: sqlite3.Connection, table_name: str) -> DatabaseTable:
    columns = tuple(
        TableColumn(
            cid=row["cid"],
            name=row["name"],
            type=row["type"],
            not_null=bool(row["notnull"]),
            default=row["dflt_value"],
            primary_key=bool(row["pk"]),
        )
        for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})")
    )
    indexes = tuple(
        TableIndex(
            name=index["name"],
            unique=bool(index["unique"]),
            origin=index["origin"],
            columns=_index_columns(connection, index["name"]),
        )
        for index in connection.execute(f"PRAGMA index_list({_quote_identifier(table_name)})")
    )
    return DatabaseTable(name=table_name, columns=columns, indexes=indexes)


def _index_columns(connection: sqlite3.Connection, index_name: str) -> tuple[str, ...]:
    return tuple(
        row["name"]
        for row in connection.execute(f"PRAGMA index_info({_quote_identifier(index_name)})")
    )


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'
