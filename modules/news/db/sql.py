"""DuckDB에 저장된 표준 RSS 항목의 CRUD 연산을 제공한다."""

from __future__ import annotations

import json
from collections.abc import Sequence
from uuid import uuid4

import duckdb

from ..schema.article import ArticleAnalysis, CanonicalArticle
from ..schema.symbol import NewsSymbol
from ..rss.models import CanonicalRssEntry, SEOUL_TIMEZONE


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


def list_rss_items_requiring_article_parse(
    connection: duckdb.DuckDBPyConnection,
    *,
    parser_versions: dict[str, str],
    limit: int = 100,
) -> tuple[CanonicalRssEntry, ...]:
    """본문이 없거나 현재 언론사 parser 버전과 다른 RSS 항목을 조회한다."""

    if limit <= 0:
        raise ValueError("limit must be greater than zero")
    if not parser_versions:
        return ()
    conditions: list[str] = []
    parameters: list[object] = []
    for publisher, version in sorted(parser_versions.items()):
        if not publisher.strip() or not version.strip():
            raise ValueError("parser publisher and version must not be empty")
        conditions.append(
            "(r.publisher = ? AND a.parser_version IS DISTINCT FROM ?)"
        )
        parameters.extend((publisher, version))
    parameters.append(limit)
    rows = connection.execute(
        f"""
        SELECT r.id, r.publisher, r.url, r.title, r.author, r.summary,
               r.domain_category, r.feed_categories, r.source_categories,
               r.published_at
        FROM rss_items AS r
        LEFT JOIN articles AS a ON a.rss_item_id = r.id
        WHERE {" OR ".join(conditions)}
        ORDER BY r.published_at, r.id
        LIMIT ?
        """,
        parameters,
    ).fetchall()
    return tuple(_row_to_item(row) for row in rows)


def insert_article(
    connection: duckdb.DuckDBPyConnection,
    article: CanonicalArticle,
) -> bool:
    """기사 본문을 parser 버전에 따라 삽입·갱신하고 변경 여부를 반환한다."""

    existing = connection.execute(
        """
        SELECT content_hash, parser_version
        FROM articles
        WHERE rss_item_id = ?
        """,
        [article.rss_item_id],
    ).fetchone()
    changed = existing != (article.content_hash, article.parser_version)
    if not changed:
        return False
    connection.execute(
        """
        INSERT INTO articles (
            rss_item_id, content, content_hash, parser_version
        ) VALUES (?, ?, ?, ?)
        ON CONFLICT (rss_item_id) DO UPDATE SET
            content = excluded.content,
            content_hash = excluded.content_hash,
            parser_version = excluded.parser_version,
            fetched_at = now()
        """,
        [
            article.rss_item_id,
            article.content,
            article.content_hash,
            article.parser_version,
        ],
    )
    return True


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
        SELECT a.rss_item_id, a.content, a.content_hash, a.parser_version
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
            parser_version=str(row[3]),
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


def replace_symbol_snapshots(
    connection: duckdb.DuckDBPyConnection,
    symbols: Sequence[NewsSymbol],
) -> int:
    """국내·해외 종목 스냅샷을 구분된 테이블에 원자적으로 교체한다."""

    _DOMESTIC = frozenset({"KOSPI", "KOSDAQ"})
    _OVERSEAS = frozenset({"NASDAQ", "NYSE", "AMEX"})
    _SUPPORTED = _DOMESTIC | _OVERSEAS

    # 중복 (market, symbol) 쌍은 나중 항목을 우선해 제거한다.
    # KIS API가 간헐적으로 동일 코드를 두 번 반환하는 경우를 처리하기 위함.
    deduped: dict[tuple[str, str], NewsSymbol] = {}
    domestic: list[NewsSymbol] = []
    overseas: list[NewsSymbol] = []
    for symbol in symbols:
        if not symbol.market:
            raise ValueError("symbol market must not be empty")
        if symbol.market not in _SUPPORTED:
            raise ValueError(
                f"unsupported symbol market: {symbol.market}. "
                f"allowed: {', '.join(sorted(_SUPPORTED))}"
            )
        deduped[(symbol.market, symbol.symbol)] = symbol

    if not deduped:
        raise ValueError("symbol master download returned no rows")

    for symbol in deduped.values():
        if symbol.market in _DOMESTIC:
            domestic.append(symbol)
        else:
            overseas.append(symbol)

    rows_by_table = {"domestic_symbols": domestic, "overseas_symbols": overseas}

    connection.execute("BEGIN TRANSACTION")
    try:
        for table_name, table_rows in rows_by_table.items():
            table_markets = tuple(dict.fromkeys(symbol.market for symbol in table_rows))
            if not table_markets:
                continue
            connection.executemany(
                f"DELETE FROM {table_name} WHERE market = ?",
                [(market,) for market in table_markets],
            )
            _bulk_insert_symbols(connection, table_name, table_rows)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    return len(deduped)


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


_SYMBOL_COLS = (
    "market", "symbol", "standard_code", "realtime_symbol", "korean_name",
    "english_name", "security_type", "currency", "exchange_id", "exchange_code",
    "exchange_name", "country_code", "listed_date", "base_price", "lot_size",
    "raw_source", "raw", "downloaded_at",
)


def _bulk_insert_symbols(
    connection: duckdb.DuckDBPyConnection,
    table_name: str,
    table_rows: Sequence[NewsSymbol],
) -> None:
    """종목 행을 컬럼 배열 + unnest 단일 쿼리로 벌크 삽입한다.

    executemany는 행마다 Python→DuckDB 왕복과 ::JSON 파싱이 발생해
    10K+ 행에서 수 초가 걸린다. unnest로 묶으면 한 번의 벡터 연산으로
    처리되어 동일 데이터셋에서 ~75배 빠르다.
    """
    if not table_rows:
        return
    cols = ", ".join(_SYMBOL_COLS)
    placeholders = ", ".join(["unnest(?)"] * len(_SYMBOL_COLS))
    connection.execute(
        f"INSERT INTO {table_name} ({cols}) SELECT {placeholders}",
        [
            [s.market for s in table_rows],
            [s.symbol for s in table_rows],
            [s.standard_code for s in table_rows],
            [s.realtime_symbol for s in table_rows],
            [s.korean_name for s in table_rows],
            [s.english_name for s in table_rows],
            [s.security_type for s in table_rows],
            [s.currency for s in table_rows],
            [s.exchange_id for s in table_rows],
            [s.exchange_code for s in table_rows],
            [s.exchange_name for s in table_rows],
            [s.country_code for s in table_rows],
            [s.listed_date for s in table_rows],
            [s.base_price for s in table_rows],
            [s.lot_size for s in table_rows],
            [s.raw_source for s in table_rows],
            [json.dumps(s.raw, ensure_ascii=False, sort_keys=True) for s in table_rows],
            [s.downloaded_at for s in table_rows],
        ],
    )


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
