"""Seed the KIS-derived domestic security catalog into PostgreSQL.

The news-intelligence app reads its security catalog (``domestic_symbols``) from
PostgreSQL instead of the local DuckDB warehouse. This one-shot script copies the
current snapshot from the existing DuckDB warehouse into the PostgreSQL database
so ``load_catalog_snapshot`` has data to serve.

Usage:
    INTELLIGENCE_DATABASE_URL=postgresql://... \
        uv run --group postgres python -m scripts.seed_intelligence_catalog \
        [--source /path/to/warehouse.duckdb]

The script is idempotent: it (re)creates the table and replaces every row so the
PostgreSQL catalog matches the DuckDB source exactly.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from modules.storage.news_intelligence.database import connect, load_env, resolve_dsn
from modules.storage.warehouse import default_warehouse_file

_COLUMNS = (
    "market",
    "symbol",
    "korean_name",
    "english_name",
    "security_type",
    "downloaded_at",
)


def _read_source(source: Path) -> list[tuple[object, ...]]:
    if not source.is_file():
        raise SystemExit(f"DuckDB warehouse not found: {source}")
    with duckdb.connect(str(source), read_only=True) as connection:
        return connection.execute(
            f"SELECT {', '.join(_COLUMNS)} FROM domestic_symbols ORDER BY market, symbol"
        ).fetchall()


def seed(dsn: str, rows: list[tuple[object, ...]]) -> int:
    connection = connect(dsn)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS domestic_symbols (
                market VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                korean_name VARCHAR,
                english_name VARCHAR,
                security_type VARCHAR,
                downloaded_at VARCHAR,
                PRIMARY KEY (market, symbol)
            )
            """
        )
        connection.execute("TRUNCATE domestic_symbols")
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO domestic_symbols "
                f"({', '.join(_COLUMNS)}) VALUES (%s, %s, %s, %s, %s, %s)",
                rows,
            )
        connection.commit()
    finally:
        connection.close()
    return len(rows)


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=default_warehouse_file(),
        help="DuckDB warehouse holding domestic_symbols (default: data dir warehouse).",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL connection string (default: INTELLIGENCE_DATABASE_URL).",
    )
    args = parser.parse_args()
    rows = _read_source(args.source)
    if not rows:
        raise SystemExit("source warehouse has no domestic_symbols rows to seed")
    count = seed(resolve_dsn(args.dsn), rows)
    print(f"seeded {count} domestic symbols into PostgreSQL")


if __name__ == "__main__":
    main()
