from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.storage.app_db import (
    APP_TABLE_NAMES,
    connect_app,
    default_app_database_file,
    init_app_database,
)
from kis_cli.storage.warehouse import (
    WAREHOUSE_TABLE_NAMES,
    connect_warehouse,
    default_warehouse_file,
    init_warehouse,
)
from kis_cli.storage.supabase_schema import (
    SUPABASE_TABLE_NAMES,
    supabase_schema_sql,
)
from kis_cli.storage.supabase import (
    SUPABASE_DSN_ENV,
    SupabaseDatabaseInitResult,
    connect_supabase,
    init_supabase_database,
    insert_supabase_ohlcv_bars,
    upsert_supabase_symbols,
)

TABLE_NAMES = WAREHOUSE_TABLE_NAMES
__all__ = [
    "APP_TABLE_NAMES",
    "SUPABASE_TABLE_NAMES",
    "SUPABASE_DSN_ENV",
    "WAREHOUSE_TABLE_NAMES",
    "DatabaseCountsResult",
    "DatabaseInitResult",
    "DatabaseSchemaResult",
    "DatabaseTable",
    "SupabaseDatabaseInitResult",
    "TableColumn",
    "TableCount",
    "TableIndex",
    "TABLE_NAMES",
    "connect",
    "connect_app",
    "connect_supabase",
    "connect_warehouse",
    "default_app_database_file",
    "default_database_file",
    "default_warehouse_file",
    "init_app_database",
    "init_database",
    "init_supabase_database",
    "init_warehouse",
    "insert_supabase_ohlcv_bars",
    "inspect_database_counts",
    "inspect_database_schema",
    "supabase_schema_sql",
    "upsert_supabase_symbols",
]


@dataclass(frozen=True)
class DatabaseInitResult:
    path: Path
    tables: tuple[str, ...]
    app_path: Path
    warehouse_path: Path


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
    return default_warehouse_file()


def connect(path: Path | None = None):
    return connect_warehouse(path)


def init_database(path: Path | None = None) -> DatabaseInitResult:
    app_path = init_app_database(
        path.expanduser().parent / "app.db" if path is not None else None
    )
    warehouse = init_warehouse(path)
    return DatabaseInitResult(
        path=warehouse.path,
        tables=warehouse.tables,
        app_path=app_path,
        warehouse_path=warehouse.path,
    )


def inspect_database_schema(path: Path | None = None) -> DatabaseSchemaResult:
    db_path = (path or default_database_file()).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"warehouse not found at {db_path}; run 'kiscli db init' first")

    with connect_warehouse(db_path) as connection:
        table_names = _table_names(connection)
        tables = tuple(_inspect_table(connection, table_name) for table_name in table_names)
    return DatabaseSchemaResult(path=db_path, tables=tables)


def inspect_database_counts(path: Path | None = None) -> DatabaseCountsResult:
    db_path = (path or default_database_file()).expanduser()
    if not db_path.exists():
        raise FileNotFoundError(f"warehouse not found at {db_path}; run 'kiscli db init' first")

    with connect_warehouse(db_path) as connection:
        tables = tuple(
            TableCount(
                name=table_name,
                rows=connection.execute(
                    f"SELECT COUNT(*) AS count FROM {_quote_identifier(table_name)}"
                ).fetchone()[0],
            )
            for table_name in _table_names(connection)
        )
    return DatabaseCountsResult(
        path=db_path,
        tables=tables,
        total_rows=sum(table.rows for table in tables),
    )


def _table_names(connection) -> list[str]:
    rows = connection.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """
    ).fetchall()
    return [row[0] for row in rows]


def _inspect_table(connection, table_name: str) -> DatabaseTable:
    column_rows = connection.execute(
        f"PRAGMA table_info({_quote_literal(table_name)})"
    ).fetchall()
    columns = tuple(
        TableColumn(
            cid=row[0],
            name=row[1],
            type=row[2],
            not_null=bool(row[3]),
            default=row[4],
            primary_key=bool(row[5]),
        )
        for row in column_rows
    )
    indexes = _unique_constraints(connection, table_name)
    return DatabaseTable(name=table_name, columns=columns, indexes=indexes)


def _unique_constraints(connection, table_name: str) -> tuple[TableIndex, ...]:
    rows = connection.execute(
        """
        SELECT constraint_name, constraint_column_names
        FROM duckdb_constraints()
        WHERE table_name = ? AND constraint_type = 'UNIQUE'
        ORDER BY constraint_name
        """,
        [table_name],
    ).fetchall()
    return tuple(
        TableIndex(
            name=row[0],
            unique=True,
            origin="u",
            columns=tuple(row[1]),
        )
        for row in rows
    )


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"
