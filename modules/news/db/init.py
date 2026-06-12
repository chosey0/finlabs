"""뉴스 수집 파이프라인에서 사용하는 DuckDB 데이터베이스를 초기화한다."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb


DEFAULT_DB_PATH = Path(__file__).resolve().with_name("news.db")
TABLE_NAMES = (
    "rss_items",
    "articles",
    "article_analyses",
    "pipeline_runs",
    "domestic_symbols",
    "overseas_symbols",
)
RSS_ITEM_SCHEMA = {
    "id": "VARCHAR",
    "publisher": "VARCHAR",
    "url": "VARCHAR",
    "title": "VARCHAR",
    "author": "VARCHAR",
    "summary": "VARCHAR",
    "domain_category": "VARCHAR",
    "feed_categories": "VARCHAR[]",
    "source_categories": "VARCHAR[]",
    "published_at": "TIMESTAMP",
    "created_at": "TIMESTAMP",
}
LEGACY_RSS_ITEM_SCHEMA = {
    key: value
    for key, value in RSS_ITEM_SCHEMA.items()
    if key not in {"domain_category", "feed_categories", "source_categories"}
}
PUBLISHED_AT_SEOUL_MIGRATION = "published_at_utc_to_asia_seoul_v1"


@dataclass(frozen=True, slots=True)
class NewsDatabaseInitResult:
    """초기화된 데이터베이스 경로와 생성된 테이블 목록을 나타낸다."""

    path: Path
    tables: tuple[str, ...]


def connect_database(path: str | Path = DEFAULT_DB_PATH) -> duckdb.DuckDBPyConnection:
    """필요하면 상위 디렉터리를 생성하고 DuckDB 연결을 연다."""

    db_path = Path(path).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(db_path))


def init_database(path: str | Path = DEFAULT_DB_PATH) -> NewsDatabaseInitResult:
    """뉴스 데이터베이스 스키마를 초기화하고 생성 결과를 반환한다."""

    db_path = Path(path).expanduser()
    with connect_database(db_path) as connection:
        create_schema(connection)
    return NewsDatabaseInitResult(path=db_path, tables=TABLE_NAMES)


def create_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """열린 연결에 뉴스 파이프라인의 영속 스키마를 생성한다."""

    existing_tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    rss_items_preexisting = "rss_items" in existing_tables
    _reset_empty_legacy_schema(connection)
    _reset_empty_legacy_articles_schema(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_items (
            id VARCHAR PRIMARY KEY,
            publisher VARCHAR NOT NULL,
            url VARCHAR NOT NULL UNIQUE,
            title VARCHAR NOT NULL,
            author VARCHAR,
            summary VARCHAR,
            domain_category VARCHAR,
            feed_categories VARCHAR[] NOT NULL DEFAULT [],
            source_categories VARCHAR[] NOT NULL DEFAULT [],
            published_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        "ALTER TABLE rss_items ADD COLUMN IF NOT EXISTS domain_category VARCHAR"
    )
    connection.execute(
        "ALTER TABLE rss_items ADD COLUMN IF NOT EXISTS feed_categories VARCHAR[]"
    )
    connection.execute(
        "ALTER TABLE rss_items ADD COLUMN IF NOT EXISTS source_categories VARCHAR[]"
    )
    for column in ("feed_categories", "source_categories"):
        connection.execute(f"UPDATE rss_items SET {column} = [] WHERE {column} IS NULL")
        connection.execute(
            f"ALTER TABLE rss_items ALTER COLUMN {column} SET DEFAULT []"
        )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            rss_item_id VARCHAR PRIMARY KEY REFERENCES rss_items(id),
            content TEXT NOT NULL,
            content_hash VARCHAR NOT NULL,
            fetched_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS article_analyses (
            rss_item_id VARCHAR PRIMARY KEY REFERENCES articles(rss_item_id),
            analyzer_version VARCHAR NOT NULL,
            content_hash VARCHAR NOT NULL,
            character_count BIGINT NOT NULL,
            word_count BIGINT NOT NULL,
            analyzed_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id VARCHAR PRIMARY KEY,
            command VARCHAR NOT NULL,
            status VARCHAR NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
            parameters VARCHAR NOT NULL,
            started_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            finished_at TIMESTAMP,
            processed_count BIGINT NOT NULL DEFAULT 0,
            created_count BIGINT NOT NULL DEFAULT 0,
            skipped_count BIGINT NOT NULL DEFAULT 0,
            error_message VARCHAR
        )
        """
    )
    _create_symbol_table(connection, "domestic_symbols")
    _create_symbol_table(connection, "overseas_symbols")
    _migrate_split_symbol_tables(connection)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            id VARCHAR PRIMARY KEY,
            applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    _migrate_published_at_to_seoul(
        connection,
        rss_items_preexisting=rss_items_preexisting,
    )


def _create_symbol_table(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
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
            raw JSON NOT NULL DEFAULT '{{}}',
            downloaded_at VARCHAR NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            UNIQUE (market, symbol)
        )
        """
    )


def _migrate_split_symbol_tables(connection: duckdb.DuckDBPyConnection) -> None:
    """초기 단일 symbols 테이블이 있으면 국내·해외 테이블로 분리한다."""

    tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    if "symbols" not in tables:
        return
    connection.execute(
        """
        INSERT INTO domestic_symbols (
            market, symbol, standard_code, realtime_symbol, korean_name,
            english_name, security_type, currency, exchange_id, exchange_code,
            exchange_name, country_code, listed_date, base_price, lot_size,
            raw_source, raw, downloaded_at
        )
        SELECT
            market, symbol, standard_code, realtime_symbol, korean_name,
            english_name, security_type, currency, exchange_id, exchange_code,
            exchange_name, country_code, listed_date, base_price, lot_size,
            raw_source, raw, downloaded_at
        FROM symbols WHERE market IN ('KOSPI', 'KOSDAQ')
        ON CONFLICT DO NOTHING
        """
    )
    connection.execute(
        """
        INSERT INTO overseas_symbols (
            market, symbol, standard_code, realtime_symbol, korean_name,
            english_name, security_type, currency, exchange_id, exchange_code,
            exchange_name, country_code, listed_date, base_price, lot_size,
            raw_source, raw, downloaded_at
        )
        SELECT
            market, symbol, standard_code, realtime_symbol, korean_name,
            english_name, security_type, currency, exchange_id, exchange_code,
            exchange_name, country_code, listed_date, base_price, lot_size,
            raw_source, raw, downloaded_at
        FROM symbols WHERE market IN ('NASDAQ', 'NYSE', 'AMEX')
        ON CONFLICT DO NOTHING
        """
    )
    connection.execute("DROP TABLE symbols")


def _migrate_published_at_to_seoul(
    connection: duckdb.DuckDBPyConnection,
    *,
    rss_items_preexisting: bool,
) -> None:
    """기존 UTC-naive 발행 시각을 서울 현지 시각으로 한 번만 변환한다."""

    applied = connection.execute(
        "SELECT 1 FROM schema_migrations WHERE id = ?",
        [PUBLISHED_AT_SEOUL_MIGRATION],
    ).fetchone()
    if applied is not None:
        return
    if rss_items_preexisting:
        connection.execute(
            "UPDATE rss_items SET published_at = published_at + INTERVAL '9 hours'"
        )
    connection.execute(
        "INSERT INTO schema_migrations (id) VALUES (?)",
        [PUBLISHED_AT_SEOUL_MIGRATION],
    )


def _reset_empty_legacy_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """기존 데이터를 삭제하지 않는 범위에서 빈 구버전 스키마를 교체한다."""

    tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    if "rss_items" not in tables:
        return

    columns = {
        row[0]: row[1] for row in connection.execute("DESCRIBE rss_items").fetchall()
    }
    if columns == RSS_ITEM_SCHEMA or columns == LEGACY_RSS_ITEM_SCHEMA:
        return

    rss_count = connection.execute("SELECT count(*) FROM rss_items").fetchone()[0]
    article_count = (
        connection.execute("SELECT count(*) FROM articles").fetchone()[0]
        if "articles" in tables
        else 0
    )
    if rss_count or article_count:
        raise RuntimeError(
            "legacy news database contains data; migrate it before initializing"
        )
    connection.execute("DROP TABLE IF EXISTS articles")
    connection.execute("DROP TABLE rss_items")


def _reset_empty_legacy_articles_schema(
    connection: duckdb.DuckDBPyConnection,
) -> None:
    """데이터가 없는 초기 ``articles`` 스텁만 현재 스키마로 교체한다."""

    tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    if "articles" not in tables:
        return

    columns = {row[0] for row in connection.execute("DESCRIBE articles").fetchall()}
    if {"rss_item_id", "content", "content_hash", "fetched_at"}.issubset(columns):
        return

    article_count = connection.execute("SELECT count(*) FROM articles").fetchone()[0]
    if article_count:
        raise RuntimeError(
            "legacy articles table contains data; migrate it before initializing"
        )
    connection.execute("DROP TABLE articles")


if __name__ == "__main__":
    result = init_database()
    print(f"Initialized {result.path} with tables: {', '.join(result.tables)}")
