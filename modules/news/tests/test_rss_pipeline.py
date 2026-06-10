"""언론사 RSS 파싱과 표준 항목 저장 흐름의 회귀 동작을 검증한다."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import duckdb
import pytest

from modules.news.db.init import create_schema
from modules.news.db.sql import (
    create_rss_item,
    delete_rss_item,
    read_rss_item,
    update_rss_item,
)
from modules.news.pipeline import (
    DEFAULT_FEED_SOURCES,
    OperationResult,
    analyze_articles,
    collect_articles,
    collect_rss,
    run_recorded_operation,
    single_writer_lock,
)
from modules.news.schema.base import CanonicalRssEntry
from modules.news.schema.etoday import EtodayRssParser
from modules.news.schema.investingcom import InvestingComRssParser
from modules.news.schema.newspim import NewspimRssParser


SEOUL = ZoneInfo("Asia/Seoul")


def _published_parsed() -> time.struct_time:
    """파서 테스트에 사용할 고정된 feedparser 형식 시각을 반환한다."""

    return time.struct_time((2026, 6, 10, 12, 0, 0, 2, 161, 0))


@pytest.mark.parametrize(
    ("parser", "raw", "publisher", "summary"),
    [
        (
            InvestingComRssParser(),
            {
                "author": "Investing.com",
                "link": "https://kr.investing.com/news/article-1",
                "published": "2026-06-10 21:00:00",
                "published_parsed": _published_parsed(),
                "title": "Investing title",
            },
            "investing.com",
            None,
        ),
        (
            EtodayRssParser(),
            {
                "author": "기자 (writer@etoday.co.kr)",
                "author_detail": {"name": "기자"},
                "link": "https://www.etoday.co.kr/news/view/1",
                "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                "published_parsed": _published_parsed(),
                "summary": "이투데이 요약",
                "title": "Etoday title",
            },
            "etoday",
            "이투데이 요약",
        ),
        (
            NewspimRssParser(),
            {
                "author": "최현민 기자",
                "link": "http://www.newspim.com/news/view/1",
                "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                "published_parsed": _published_parsed(),
                "summary": "뉴스핌 요약",
                "title": "Newspim title",
            },
            "newspim",
            "뉴스핌 요약",
        ),
    ],
)
def test_provider_parser_returns_canonical_entry(parser, raw, publisher, summary):
    """각 언론사 파서가 동일한 표준 RSS 항목을 반환하는지 검증한다."""

    entry = parser.parse(raw)

    assert isinstance(entry, CanonicalRssEntry)
    assert entry.publisher == publisher
    assert entry.summary == summary
    assert entry.id == hashlib.sha256(entry.url.encode("utf-8")).hexdigest()
    assert entry.published_at == datetime(2026, 6, 10, 21, 0, tzinfo=SEOUL)
    assert entry.published_at.tzinfo == SEOUL


def test_parser_rejects_invalid_url_before_database_write():
    """잘못된 기사 URL이 데이터베이스 적재 전에 거부되는지 검증한다."""

    raw = {
        "author": "Investing.com",
        "link": "invalid-url",
        "published": "2026-06-10 21:00:00",
        "published_parsed": _published_parsed(),
        "title": "Title",
    }

    with pytest.raises(ValueError, match=r"HTTP\(S\) URL"):
        InvestingComRssParser().parse(raw)


def test_crud_uses_one_canonical_contract():
    """CRUD 연산이 하나의 표준 RSS 항목 계약을 유지하는지 검증한다."""

    connection = duckdb.connect(":memory:")
    create_schema(connection)
    item = InvestingComRssParser().parse(
        {
            "author": "Investing.com",
            "link": "https://kr.investing.com/news/article-1",
            "published": "2026-06-10 21:00:00",
            "published_parsed": _published_parsed(),
            "title": "Original title",
        }
    )

    assert create_rss_item(connection, item) == item.id
    assert create_rss_item(connection, item) == item.id
    assert connection.execute("SELECT count(*) FROM rss_items").fetchone() == (1,)
    assert read_rss_item(connection, item.id) == item

    updated = CanonicalRssEntry(
        id=item.id,
        publisher=item.publisher,
        url=item.url,
        title="Updated title",
        author=item.author,
        summary="Updated summary",
        published_at=item.published_at,
    )
    assert update_rss_item(connection, updated) is True
    assert read_rss_item(connection, item.id) == updated
    assert delete_rss_item(connection, item.id) is True
    assert read_rss_item(connection, item.id) is None


def test_naive_korean_feed_time_is_interpreted_as_seoul_time():
    """시간대가 없는 한국 RSS 발행 시각을 서울 현지 시각으로 해석한다."""

    entry = InvestingComRssParser().parse(
        {
            "author": "Investing.com",
            "link": "https://kr.investing.com/news/article-seoul-time",
            "published": "2026-06-10 21:00:00",
            "title": "Seoul time",
        }
    )

    assert entry.published_at == datetime(2026, 6, 10, 21, 0, tzinfo=SEOUL)


def test_three_pipeline_stages_are_idempotent():
    """RSS 수집, 본문 수집, 분석을 재실행해도 중복 행이 생기지 않는다."""

    connection = duckdb.connect(":memory:")
    create_schema(connection)
    raw_entry = {
        "author": "Investing.com",
        "link": "https://kr.investing.com/news/article-1",
        "published": "2026-06-10 21:00:00",
        "published_parsed": _published_parsed(),
        "title": "Pipeline title",
    }

    def load_feed(url):
        assert url == DEFAULT_FEED_SOURCES[0].url
        return SimpleNamespace(entries=[raw_entry], bozo=False)

    sources = (DEFAULT_FEED_SOURCES[0],)
    first_rss = collect_rss(connection, sources=sources, feed_loader=load_feed)
    second_rss = collect_rss(connection, sources=sources, feed_loader=load_feed)
    first_articles = collect_articles(
        connection,
        fetch_html=lambda url: (
            "<html><style>ignored</style><article>Pipeline body text</article>"
            "<script>ignored()</script></html>"
        ),
    )
    second_articles = collect_articles(
        connection,
        fetch_html=lambda url: pytest.fail(f"unexpected refetch: {url}"),
    )
    first_analysis = analyze_articles(connection)
    second_analysis = analyze_articles(connection)

    assert first_rss == OperationResult(processed=1, created=1, skipped=0)
    assert second_rss == OperationResult(processed=1, created=0, skipped=1)
    assert first_articles == OperationResult(processed=1, created=1, skipped=0)
    assert second_articles == OperationResult(processed=0, created=0, skipped=0)
    assert first_analysis == OperationResult(processed=1, created=1, skipped=0)
    assert second_analysis == OperationResult(processed=0, created=0, skipped=0)
    assert connection.execute("SELECT content FROM articles").fetchone() == (
        "Pipeline body text",
    )
    assert connection.execute(
        "SELECT character_count, word_count FROM article_analyses"
    ).fetchone() == (18, 3)


def test_recorded_operation_persists_success_and_failure():
    """각 단계의 성공·실패 상태와 오류 메시지가 실행 이력에 남는다."""

    connection = duckdb.connect(":memory:")
    create_schema(connection)

    result = run_recorded_operation(
        connection,
        command="analyze",
        parameters={"limit": 10},
        operation=lambda: OperationResult(processed=2, created=1, skipped=1),
    )

    def fail_operation():
        raise RuntimeError("collector failed")

    with pytest.raises(RuntimeError, match="collector failed"):
        run_recorded_operation(
            connection,
            command="collect-rss",
            parameters={},
            operation=fail_operation,
        )

    rows = connection.execute(
        """
        SELECT command, status, processed_count, created_count,
               skipped_count, error_message
        FROM pipeline_runs
        ORDER BY started_at, command
        """
    ).fetchall()
    assert result == OperationResult(processed=2, created=1, skipped=1)
    assert rows == [
        ("analyze", "succeeded", 2, 1, 1, None),
        ("collect-rss", "failed", 0, 0, 0, "RuntimeError: collector failed"),
    ]


def test_create_schema_replaces_only_empty_legacy_articles_table():
    """초기 빈 articles 스텁은 확장하되 기존 데이터는 암묵적으로 삭제하지 않는다."""

    connection = duckdb.connect(":memory:")
    connection.execute(
        """
        CREATE TABLE rss_items (
            id VARCHAR PRIMARY KEY,
            publisher VARCHAR NOT NULL,
            url VARCHAR NOT NULL UNIQUE,
            title VARCHAR NOT NULL,
            author VARCHAR,
            summary VARCHAR,
            published_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.execute(
        "CREATE TABLE articles (rss_item_id VARCHAR PRIMARY KEY REFERENCES rss_items(id))"
    )

    create_schema(connection)

    columns = {row[0] for row in connection.execute("DESCRIBE articles").fetchall()}
    assert columns == {"rss_item_id", "content", "content_hash", "fetched_at"}


def test_create_schema_migrates_existing_utc_published_at_to_seoul_once():
    """구버전 UTC-naive 발행 시각을 한 번만 서울 시각으로 변환한다."""

    connection = duckdb.connect(":memory:")
    create_schema(connection)
    connection.execute("DELETE FROM schema_migrations")
    connection.execute(
        """
        INSERT INTO rss_items (
            id, publisher, url, title, published_at
        ) VALUES (?, 'investing.com', ?, 'Legacy', TIMESTAMP '2026-06-10 12:00:00')
        """,
        ["a" * 64, "https://example.com/legacy"],
    )

    create_schema(connection)
    first_value = connection.execute(
        "SELECT published_at FROM rss_items"
    ).fetchone()[0]
    create_schema(connection)
    second_value = connection.execute(
        "SELECT published_at FROM rss_items"
    ).fetchone()[0]

    assert first_value == datetime(2026, 6, 10, 21, 0)
    assert second_value == first_value


def test_single_writer_lock_rejects_overlapping_pipeline(tmp_path):
    """같은 DuckDB를 대상으로 겹치는 파이프라인 실행을 즉시 거부한다."""

    database_path = tmp_path / "news.duckdb"

    with single_writer_lock(database_path):
        with pytest.raises(RuntimeError, match="another news pipeline process"):
            with single_writer_lock(database_path):
                pytest.fail("overlapping writer lock was acquired")
