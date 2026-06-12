"""DuckDB에 저장된 표준 RSS 항목의 CRUD 연산을 제공한다."""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import uuid4

import duckdb

from ..schema.article import ArticleAnalysis, CanonicalArticle
from ..schema.base import CanonicalRssEntry, SEOUL_TIMEZONE


def create_rss_item(
    connection: duckdb.DuckDBPyConnection,
    item: CanonicalRssEntry,
) -> str:
    """RSS 항목을 중복 없이 삽입하고 결정적 ID를 반환한다."""

    insert_rss_item(connection, item)
    return item.id


def insert_rss_item(
    connection: duckdb.DuckDBPyConnection,
    item: CanonicalRssEntry,
) -> bool:
    """RSS 항목을 삽입하고 새 행이 생성되었는지 반환한다."""

    row = connection.execute(
        """
        INSERT INTO rss_items (
            id, publisher, url, title, author, summary, domain_category,
            feed_categories, source_categories, published_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO NOTHING
        RETURNING id
        """,
        _item_values(item),
    ).fetchone()
    if row is not None:
        return True
    existing = read_rss_item(connection, item.id)
    if existing is None:
        return False
    merged = CanonicalRssEntry(
        id=existing.id,
        publisher=existing.publisher,
        url=existing.url,
        title=existing.title,
        author=existing.author,
        summary=existing.summary,
        published_at=existing.published_at,
        domain_category=existing.domain_category or item.domain_category,
        feed_categories=existing.feed_categories + item.feed_categories,
        source_categories=existing.source_categories + item.source_categories,
    )
    if merged != existing:
        update_rss_item(connection, merged)
    return False


def read_rss_item(
    connection: duckdb.DuckDBPyConnection,
    item_id: str,
) -> CanonicalRssEntry | None:
    """ID로 RSS 항목을 조회하고 존재하지 않으면 ``None``을 반환한다."""

    row = connection.execute(
        """
        SELECT id, publisher, url, title, author, summary, domain_category,
               feed_categories, source_categories, published_at
        FROM rss_items
        WHERE id = ?
        """,
        [item_id],
    ).fetchone()
    return _row_to_item(row) if row is not None else None


def update_rss_item(
    connection: duckdb.DuckDBPyConnection,
    item: CanonicalRssEntry,
) -> bool:
    """RSS 항목을 갱신하고 대상 행의 존재 여부를 반환한다."""

    row = connection.execute(
        """
        UPDATE rss_items
        SET publisher = ?, url = ?, title = ?, author = ?, summary = ?,
            domain_category = ?, feed_categories = ?, source_categories = ?,
            published_at = ?
        WHERE id = ?
        RETURNING id
        """,
        [
            item.publisher,
            item.url,
            item.title,
            item.author,
            item.summary,
            item.domain_category,
            list(item.feed_categories),
            list(item.source_categories),
            item.published_at.astimezone(SEOUL_TIMEZONE).replace(tzinfo=None),
            item.id,
        ],
    ).fetchone()
    return row is not None


def delete_rss_item(
    connection: duckdb.DuckDBPyConnection,
    item_id: str,
) -> bool:
    """RSS 항목을 삭제하고 대상 행의 존재 여부를 반환한다."""

    row = connection.execute(
        "DELETE FROM rss_items WHERE id = ? RETURNING id",
        [item_id],
    ).fetchone()
    return row is not None


def list_rss_items(
    connection: duckdb.DuckDBPyConnection,
    *,
    publisher: str | None = None,
    limit: int = 100,
) -> tuple[CanonicalRssEntry, ...]:
    """최신 RSS 항목을 언론사 필터와 개수 제한에 따라 조회한다."""

    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if publisher is None:
        rows = connection.execute(
            """
            SELECT id, publisher, url, title, author, summary, domain_category,
                   feed_categories, source_categories, published_at
            FROM rss_items
            ORDER BY published_at DESC, id
            LIMIT ?
            """,
            [limit],
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT id, publisher, url, title, author, summary, domain_category,
                   feed_categories, source_categories, published_at
            FROM rss_items
            WHERE publisher = ?
            ORDER BY published_at DESC, id
            LIMIT ?
            """,
            [publisher, limit],
        ).fetchall()
    return tuple(_row_to_item(row) for row in rows)


def list_rss_items_without_articles(
    connection: duckdb.DuckDBPyConnection,
    *,
    limit: int = 100,
) -> tuple[CanonicalRssEntry, ...]:
    """아직 본문이 저장되지 않은 RSS 항목을 오래된 순서로 조회한다."""

    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    rows = connection.execute(
        """
        SELECT r.id, r.publisher, r.url, r.title, r.author, r.summary,
               r.domain_category, r.feed_categories, r.source_categories,
               r.published_at
        FROM rss_items AS r
        LEFT JOIN articles AS a ON a.rss_item_id = r.id
        WHERE a.rss_item_id IS NULL
        ORDER BY r.published_at, r.id
        LIMIT ?
        """,
        [limit],
    ).fetchall()
    return tuple(_row_to_item(row) for row in rows)


def insert_article(
    connection: duckdb.DuckDBPyConnection,
    article: CanonicalArticle,
) -> bool:
    """기사 본문을 중복 없이 저장하고 새 행 생성 여부를 반환한다."""

    row = connection.execute(
        """
        INSERT INTO articles (rss_item_id, content, content_hash)
        VALUES (?, ?, ?)
        ON CONFLICT (rss_item_id) DO NOTHING
        RETURNING rss_item_id
        """,
        [article.rss_item_id, article.content, article.content_hash],
    ).fetchone()
    return row is not None


def list_articles_without_current_analysis(
    connection: duckdb.DuckDBPyConnection,
    *,
    analyzer_version: str,
    limit: int = 100,
) -> tuple[CanonicalArticle, ...]:
    """현재 본문 해시와 분석기 버전에 맞는 분석이 없는 기사를 조회한다."""

    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    rows = connection.execute(
        """
        SELECT a.rss_item_id, a.content, a.content_hash
        FROM articles AS a
        LEFT JOIN article_analyses AS x
          ON x.rss_item_id = a.rss_item_id
         AND x.content_hash = a.content_hash
         AND x.analyzer_version = ?
        WHERE x.rss_item_id IS NULL
        ORDER BY a.fetched_at, a.rss_item_id
        LIMIT ?
        """,
        [analyzer_version, limit],
    ).fetchall()
    return tuple(
        CanonicalArticle(
            rss_item_id=str(row[0]),
            content=str(row[1]),
            content_hash=str(row[2]),
        )
        for row in rows
    )


def upsert_article_analysis(
    connection: duckdb.DuckDBPyConnection,
    analysis: ArticleAnalysis,
) -> None:
    """기사별 최신 기본 분석 결과를 멱등하게 저장한다."""

    connection.execute(
        """
        INSERT INTO article_analyses (
            rss_item_id, analyzer_version, content_hash,
            character_count, word_count
        ) VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (rss_item_id) DO UPDATE SET
            analyzer_version = excluded.analyzer_version,
            content_hash = excluded.content_hash,
            character_count = excluded.character_count,
            word_count = excluded.word_count,
            analyzed_at = now()
        """,
        [
            analysis.rss_item_id,
            analysis.analyzer_version,
            analysis.content_hash,
            analysis.character_count,
            analysis.word_count,
        ],
    )


def start_pipeline_run(
    connection: duckdb.DuckDBPyConnection,
    *,
    command: str,
    parameters: dict[str, object],
) -> str:
    """실행 이력을 ``running`` 상태로 생성하고 실행 ID를 반환한다."""

    run_id = str(uuid4())
    connection.execute(
        """
        INSERT INTO pipeline_runs (id, command, status, parameters)
        VALUES (?, ?, 'running', ?)
        """,
        [run_id, command, json.dumps(parameters, ensure_ascii=False, sort_keys=True)],
    )
    return run_id


def finish_pipeline_run(
    connection: duckdb.DuckDBPyConnection,
    run_id: str,
    *,
    status: str,
    processed_count: int = 0,
    created_count: int = 0,
    skipped_count: int = 0,
    error_message: str | None = None,
) -> None:
    """실행 이력을 성공 또는 실패 상태와 처리 건수로 완료한다."""

    if status not in {"succeeded", "failed"}:
        raise ValueError("status must be succeeded or failed")
    connection.execute(
        """
        UPDATE pipeline_runs
        SET status = ?, finished_at = current_timestamp,
            processed_count = ?, created_count = ?, skipped_count = ?,
            error_message = ?
        WHERE id = ?
        """,
        [
            status,
            processed_count,
            created_count,
            skipped_count,
            error_message,
            run_id,
        ],
    )


def _item_values(item: CanonicalRssEntry) -> list[object]:
    """표준 RSS 항목을 DuckDB 쿼리의 순서가 있는 매개변수로 변환한다."""

    return [
        item.id,
        item.publisher,
        item.url,
        item.title,
        item.author,
        item.summary,
        item.domain_category,
        list(item.feed_categories),
        list(item.source_categories),
        item.published_at.astimezone(SEOUL_TIMEZONE).replace(tzinfo=None),
    ]


def _row_to_item(row: Sequence[object]) -> CanonicalRssEntry:
    """DuckDB 조회 행을 검증된 표준 RSS 항목으로 변환한다."""

    return CanonicalRssEntry(
        id=str(row[0]),
        publisher=str(row[1]),
        url=str(row[2]),
        title=str(row[3]),
        author=None if row[4] is None else str(row[4]),
        summary=None if row[5] is None else str(row[5]),
        domain_category=None if row[6] is None else str(row[6]),
        feed_categories=tuple(row[7]),
        source_categories=tuple(row[8]),
        published_at=row[9].replace(tzinfo=SEOUL_TIMEZONE),
    )
