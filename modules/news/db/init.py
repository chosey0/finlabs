"""뉴스 수집 파이프라인이 사용하는 PostgreSQL 스키마를 초기화한다.

뉴스 파이프라인은 finlabs_intelligence와 동일한 Supabase PostgreSQL 인스턴스를
저장소로 공유한다. 연결 문자열은 ``INTELLIGENCE_DATABASE_URL`` 환경 변수에서
해석한다(``modules.storage.news_intelligence.database.resolve_dsn``).
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from modules.storage.news_intelligence.database import load_env, resolve_dsn

TABLE_NAMES = (
    "rss_items",
    "rss_feed_cooldowns",
    "articles",
    "article_analyses",
    "article_entities",
    "article_entity_extractions",
    "pipeline_runs",
    "domestic_symbols",
    "overseas_symbols",
)


@dataclass(frozen=True, slots=True)
class NewsDatabaseInitResult:
    """초기화된 데이터베이스 식별자와 생성된 테이블 목록을 나타낸다."""

    dsn: str
    tables: tuple[str, ...]


def connect_database(dsn: str | None = None) -> psycopg.Connection:
    """Supabase PostgreSQL 연결을 연다.

    DuckDB가 문장마다 자동 커밋했던 동작을 보존하도록 ``autocommit=True``로
    연결한다. 원자성이 필요한 연산은 ``connection.transaction()``으로 감싼다.
    """

    return psycopg.connect(resolve_dsn(dsn), autocommit=True)


def init_database(dsn: str | None = None) -> NewsDatabaseInitResult:
    """뉴스 데이터베이스 스키마를 초기화하고 생성 결과를 반환한다."""

    resolved = resolve_dsn(dsn)
    with connect_database(resolved) as connection:
        create_schema(connection)
    return NewsDatabaseInitResult(dsn=resolved, tables=TABLE_NAMES)


def create_schema(connection: psycopg.Connection) -> None:
    """열린 연결에 뉴스 파이프라인의 영속 스키마를 멱등하게 생성한다."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_items (
            id text PRIMARY KEY,
            publisher text NOT NULL,
            url text NOT NULL UNIQUE,
            title text NOT NULL,
            author text,
            summary text,
            domain_category text,
            feed_categories text[] NOT NULL DEFAULT '{}',
            source_categories text[] NOT NULL DEFAULT '{}',
            published_at timestamp NOT NULL,
            created_at timestamp NOT NULL DEFAULT current_timestamp
        )
        """
    )
    # 요청 제한(HTTP 429)에 걸린 피드를 점증 쿨다운으로 건너뛰기 위한 상태.
    # collect-rss는 매 회차 새 프로세스로 돌 수 있으므로 streak/skip_until을
    # 공유 DB에 영속해 회차 사이에도 쿨다운이 유지되게 한다. 시간 비교는 모두
    # 서버측 ``now()``로 하여 클라이언트 시계에 의존하지 않는다.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS rss_feed_cooldowns (
            url text PRIMARY KEY,
            publisher text NOT NULL,
            streak integer NOT NULL,
            skip_until timestamptz NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS articles (
            rss_item_id text PRIMARY KEY REFERENCES rss_items(id),
            content text NOT NULL,
            content_hash text NOT NULL,
            parser_version text NOT NULL,
            fetched_at timestamp NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS article_analyses (
            rss_item_id text PRIMARY KEY REFERENCES articles(rss_item_id),
            analyzer_version text NOT NULL,
            content_hash text NOT NULL,
            character_count bigint NOT NULL,
            word_count bigint NOT NULL,
            analyzed_at timestamp NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS article_entities (
            rss_item_id text NOT NULL REFERENCES articles(rss_item_id),
            entity_type text NOT NULL,
            entity_name text NOT NULL,
            ticker text,
            confidence double precision NOT NULL,
            PRIMARY KEY (rss_item_id, entity_type, entity_name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS article_entity_extractions (
            rss_item_id text PRIMARY KEY REFERENCES articles(rss_item_id),
            extractor_version text NOT NULL,
            content_hash text NOT NULL,
            entity_count bigint NOT NULL,
            extracted_at timestamp NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id text PRIMARY KEY,
            command text NOT NULL,
            status text NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
            parameters text NOT NULL,
            started_at timestamp NOT NULL DEFAULT current_timestamp,
            finished_at timestamp,
            processed_count bigint NOT NULL DEFAULT 0,
            created_count bigint NOT NULL DEFAULT 0,
            skipped_count bigint NOT NULL DEFAULT 0,
            error_message text
        )
        """
    )
    _create_symbol_table(connection, "domestic_symbols")
    _create_symbol_table(connection, "overseas_symbols")


def _create_symbol_table(connection: psycopg.Connection, table_name: str) -> None:
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            market text NOT NULL,
            symbol text NOT NULL,
            standard_code text,
            realtime_symbol text,
            korean_name text,
            english_name text,
            security_type text,
            currency text,
            exchange_id text,
            exchange_code text,
            exchange_name text,
            country_code text,
            listed_date text,
            base_price bigint,
            lot_size bigint,
            raw_source text NOT NULL DEFAULT '',
            raw jsonb NOT NULL DEFAULT '{{}}'::jsonb,
            downloaded_at text NOT NULL,
            created_at timestamp NOT NULL DEFAULT current_timestamp,
            updated_at timestamp NOT NULL DEFAULT current_timestamp,
            UNIQUE (market, symbol)
        )
        """
    )


if __name__ == "__main__":
    load_env()
    result = init_database()
    print(f"Initialized news schema with tables: {', '.join(result.tables)}")
