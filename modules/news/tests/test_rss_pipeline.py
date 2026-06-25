"""언론사 RSS 파싱과 표준 항목 저장 흐름의 회귀 동작을 검증한다."""

from __future__ import annotations

import hashlib
import threading
import time
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest

from modules.news.articles.parsers import ARTICLE_PARSERS, SelectorArticleParser
from modules.news.db.sql import (
    create_rss_item,
    delete_rss_item,
    feed_cooldown_minutes,
    list_active_feed_cooldowns,
    read_rss_item,
    register_feed_rate_limit,
    update_rss_item,
)
from modules.news.pipeline import (
    DEFAULT_FEED_SOURCES,
    FeedSource,
    OperationResult,
    analyze_articles,
    collect_articles,
    collect_rss,
    run_recorded_operation,
)
from modules.news.rss.parsers import PARSERS
from modules.news.rss.models import CanonicalRssEntry


SEOUL = ZoneInfo("Asia/Seoul")


def _published_parsed() -> time.struct_time:
    """파서 테스트에 사용할 고정된 feedparser 형식 시각을 반환한다."""

    return time.struct_time((2026, 6, 10, 12, 0, 0, 2, 161, 0))


@pytest.mark.parametrize(
    ("parser", "raw", "publisher", "summary"),
    [
        (
            PARSERS["investing.com"],
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
            PARSERS["edaily"],
            {
                "author": "최효은",
                "author_detail": {"name": "최효은"},
                "link": "https://www.edaily.co.kr/News/Read?newsId=1",
                "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                "published_parsed": _published_parsed(),
                "summary": "이데일리 요약",
                "title": "Edaily title",
            },
            "edaily",
            "이데일리 요약",
        ),
        (
            PARSERS["etoday"],
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
            PARSERS["hankyung"],
            {
                "author": "한국경제 기자",
                "link": "https://www.hankyung.com/article/1",
                "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                "title": "Hankyung title",
            },
            "hankyung",
            None,
        ),
        (
            PARSERS["newspim"],
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
        (
            PARSERS["sedaily"],
            {
                "author": "서울경제 기자",
                "link": "https://www.sedaily.com/article/1",
                "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                "title": "Sedaily title",
            },
            "sedaily",
            None,
        ),
        (
            PARSERS["donga"],
            {
                "link": "https://www.donga.com/news/article/all/1",
                "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                "summary": "<img src='https://dimg.donga.com/x.jpg'> 본문 일부",
                "title": "Donga title",
            },
            "donga",
            None,
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


def test_parser_preserves_source_categories_without_normalizing(news_connection):
    """XML category 값은 매체 원문 그대로 중복 없이 보존한다."""

    entry = PARSERS["edaily"].parse(
        {
            "author": "기자",
            "link": "https://www.edaily.co.kr/News/Read?newsId=category",
            "published": "Wed, 10 Jun 2026 21:00:00 +0900",
            "summary": "요약",
            "tags": [{"term": "증권"}, {"term": "증권"}, {"term": "금융·재테크"}],
            "title": "Category title",
        }
    )

    assert entry.source_categories == ("증권", "금융·재테크")


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
        PARSERS["investing.com"].parse(raw)


def test_default_feed_sources_include_edaily():
    """기본 RSS 수집 대상에 이데일리 피드가 포함되는지 검증한다."""

    sources = {source.publisher: source.url for source in DEFAULT_FEED_SOURCES}

    assert sources["edaily"] == "http://rss.edaily.co.kr/edaily_news.xml"


def test_default_feed_sources_include_configured_categories():
    """제공된 카테고리별 RSS URL과 Investing.com 도메인을 기본값으로 유지한다."""

    categorized = {
        (source.publisher, source.feed_category): source.url
        for source in DEFAULT_FEED_SOURCES
        if source.feed_category is not None
    }

    assert categorized[("investing.com", "내부자거래")].endswith("news_357.rss")
    assert categorized[("investing.com", "경제 뉴스")].endswith("news_14.rss")
    assert categorized[("etoday", "금융")].endswith("finance_news.xml")
    assert categorized[("etoday", "문화/라이프")].endswith("culture-life_news.xml")
    assert categorized[("newspim", "정치")].endswith("category/101")
    assert categorized[("newspim", "스포츠")].endswith("category/111")
    assert categorized[("hankyung", "증권")].endswith("feed/finance")
    assert categorized[("hankyung", "연예")].endswith("feed/entertainment")
    assert categorized[("sedaily", "증권")].endswith("rss/finance")
    assert categorized[("sedaily", "연예")].endswith("rss/entertainment")
    assert categorized[("donga", "경제")].endswith("economy.xml")
    assert categorized[("donga", "건강")].endswith("health.xml")
    assert categorized[("donga", "사회")].endswith("national.xml")
    assert all(
        source.domain_category == "금융"
        for source in DEFAULT_FEED_SOURCES
        if source.publisher == "investing.com"
    )

    uncategorized = {
        source.publisher: source.url
        for source in DEFAULT_FEED_SOURCES
        if source.feed_category is None
    }
    assert uncategorized["hankyung"] == "https://www.hankyung.com/feed/all-news"
    assert uncategorized["sedaily"] == "https://www.sedaily.com/rss/newsall"
    assert uncategorized["donga"] == "https://rss.donga.com/total.xml"


def test_crud_uses_one_canonical_contract(news_connection):
    """CRUD 연산이 하나의 표준 RSS 항목 계약을 유지하는지 검증한다."""

    connection = news_connection
    item = PARSERS["investing.com"].parse(
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


def test_naive_korean_feed_time_is_interpreted_as_seoul_time(news_connection):
    """시간대가 없는 한국 RSS 발행 시각을 서울 현지 시각으로 해석한다."""

    entry = PARSERS["investing.com"].parse(
        {
            "author": "Investing.com",
            "link": "https://kr.investing.com/news/article-seoul-time",
            "published": "2026-06-10 21:00:00",
            "title": "Seoul time",
        }
    )

    assert entry.published_at == datetime(2026, 6, 10, 21, 0, tzinfo=SEOUL)


_EDAILY_SOURCE = next(
    source for source in DEFAULT_FEED_SOURCES if source.publisher == "edaily"
)


def _edaily_html(body: str) -> str:
    return (
        "<html><style>ignored</style><div id='contents'>"
        "<section class='position_r center1080'><section class='aside_left'>"
        "<div class='article_news'><div class='newscontainer'>"
        f"<div class='news_body'>{body}<script>ignored()</script></div>"
        "</div></div></section></section></div></html>"
    )


def _edaily_entry(link: str, title: str) -> dict:
    return {
        "author": "edaily",
        "link": link,
        "published": "2026-06-10 21:00:00",
        "published_parsed": _published_parsed(),
        "title": title,
    }


def test_three_pipeline_stages_are_idempotent(news_connection):
    """RSS 수집, 본문 수집, 분석을 재실행해도 중복 행이 생기지 않는다."""

    connection = news_connection
    raw_entry = _edaily_entry(
        "https://www.edaily.co.kr/news/article-1", "Pipeline title"
    )

    def load_feed(url):
        assert url == _EDAILY_SOURCE.url
        return SimpleNamespace(entries=[raw_entry], bozo=False)

    sources = (_EDAILY_SOURCE,)
    first_rss = collect_rss(connection, sources=sources, feed_loader=load_feed)
    second_rss = collect_rss(connection, sources=sources, feed_loader=load_feed)
    first_articles = collect_articles(
        connection,
        fetch_html=lambda url: _edaily_html("Pipeline body text"),
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
    assert connection.execute("SELECT parser_version FROM articles").fetchone() == (
        ARTICLE_PARSERS["edaily"].version,
    )
    assert connection.execute(
        "SELECT character_count, word_count FROM article_analyses"
    ).fetchone() == (18, 3)


def test_analyze_reports_pending_and_item_progress(news_connection):
    connection = news_connection
    entries = [
        _edaily_entry(
            f"https://www.edaily.co.kr/news/analyze-progress-{index}",
            f"Analyze title {index}",
        )
        for index in range(2)
    ]
    collect_rss(
        connection,
        sources=(_EDAILY_SOURCE,),
        feed_loader=lambda url: SimpleNamespace(entries=entries, bozo=False),
    )
    collect_articles(
        connection,
        fetch_html=lambda url: _edaily_html("Analyze body"),
    )
    pending_batches = []
    item_results = []

    result = analyze_articles(
        connection,
        on_pending=pending_batches.append,
        on_item_result=lambda article, title, item_result: item_results.append(
            (article.rss_item_id, title, item_result.created)
        ),
    )

    assert result == OperationResult(processed=2, created=2, skipped=0)
    assert len(pending_batches) == 1
    assert len(pending_batches[0]) == 2
    assert {title for _, title, _ in item_results} == {
        "Analyze title 0",
        "Analyze title 1",
    }


def test_analyze_all_processes_every_pending_article(news_connection):
    connection = news_connection
    entries = [
        _edaily_entry(
            f"https://www.edaily.co.kr/news/analyze-all-{index}",
            f"Analyze all {index}",
        )
        for index in range(105)
    ]
    collect_rss(
        connection,
        sources=(_EDAILY_SOURCE,),
        feed_loader=lambda url: SimpleNamespace(entries=entries, bozo=False),
    )
    collect_articles(
        connection,
        limit=None,
        fetch_html=lambda url: _edaily_html("Analyze all body"),
    )

    result = analyze_articles(connection, limit=None)

    assert result == OperationResult(processed=105, created=105, skipped=0)
    assert connection.execute("SELECT count(*) FROM article_analyses").fetchone() == (
        105,
    )


@pytest.mark.parametrize(
    ("extra_args", "expected_limit"),
    [([], 100), (["--limit", "7"], 7), (["--all"], None)],
)
def test_analyze_cli_passes_dsn_and_limit_to_progress_flow(
    monkeypatch,
    extra_args,
    expected_limit,
):
    from typer.testing import CliRunner

    from modules.news import main as news_main

    calls = []
    monkeypatch.setattr(
        news_main,
        "_analyze_with_progress",
        lambda dsn, limit: calls.append((dsn, limit)),
    )
    dsn = "postgresql://example/news"

    result = CliRunner().invoke(
        news_main.app,
        ["analyze", "--dsn", dsn, *extra_args],
    )

    assert result.exit_code == 0
    assert calls == [(dsn, expected_limit)]


def test_collect_articles_reprocesses_when_parser_version_changes(news_connection):
    """파서 버전이 바뀌면 기존 본문을 다시 가져와 같은 행을 갱신한다."""

    connection = news_connection
    raw_entry = _edaily_entry(
        "https://www.edaily.co.kr/news/reparse-version", "Reparse title"
    )
    collect_rss(
        connection,
        sources=(_EDAILY_SOURCE,),
        feed_loader=lambda url: SimpleNamespace(entries=[raw_entry], bozo=False),
    )
    html = _edaily_html("Versioned body")
    first = collect_articles(connection, fetch_html=lambda url: html)
    current = ARTICLE_PARSERS["edaily"]
    upgraded = SelectorArticleParser(
        publisher=current.publisher,
        version="edaily-news-body-v2",
        selectors=current.selectors,
    )
    second = collect_articles(
        connection,
        fetch_html=lambda url: html,
        article_parsers={**ARTICLE_PARSERS, "edaily": upgraded},
    )

    assert first == OperationResult(processed=1, created=1, skipped=0)
    assert second == OperationResult(processed=1, created=1, skipped=0)
    assert connection.execute(
        "SELECT count(*), parser_version FROM articles GROUP BY parser_version"
    ).fetchone() == (1, "edaily-news-body-v2")


def test_collect_articles_isolates_per_article_failures_and_retries(news_connection):
    """기사 한 건의 수집 실패가 배치를 중단시키지 않고 다음 실행에서 재시도된다."""

    connection = news_connection
    failing_url = "https://www.edaily.co.kr/news/blocked"
    entries = [
        _edaily_entry(failing_url, "Blocked title"),
        _edaily_entry("https://www.edaily.co.kr/news/ok", "OK title"),
    ]
    collect_rss(
        connection,
        sources=(_EDAILY_SOURCE,),
        feed_loader=lambda url: SimpleNamespace(entries=entries, bozo=False),
    )

    def failing_fetch(url):
        if url == failing_url:
            raise httpx.HTTPError("403 Forbidden")
        return _edaily_html("Recovered body")

    first = collect_articles(connection, fetch_html=failing_fetch)
    second = collect_articles(
        connection,
        fetch_html=lambda url: _edaily_html("Recovered body"),
    )

    assert (first.processed, first.created, first.skipped) == (2, 1, 1)
    assert len(first.errors) == 1
    assert "403 Forbidden" in first.errors[0]
    assert failing_url in first.errors[0]
    assert second == OperationResult(processed=1, created=1, skipped=0)
    assert connection.execute("SELECT count(*) FROM articles").fetchone() == (2,)


def test_collect_articles_reports_pending_and_per_item_results(news_connection):
    """진행 표시용 콜백이 수집 대상과 기사별 결과를 순서대로 전달한다."""

    connection = news_connection
    failing_url = "https://www.edaily.co.kr/news/progress-fail"
    entries = [
        _edaily_entry(failing_url, "Progress fail title"),
        _edaily_entry("https://www.edaily.co.kr/news/progress-ok", "Progress ok title"),
    ]
    collect_rss(
        connection,
        sources=(_EDAILY_SOURCE,),
        feed_loader=lambda url: SimpleNamespace(entries=entries, bozo=False),
    )
    pending_batches = []
    item_results = []

    def failing_fetch(url):
        if url == failing_url:
            raise httpx.HTTPError("403 Forbidden")
        return _edaily_html("Progress body")

    collect_articles(
        connection,
        fetch_html=failing_fetch,
        on_pending=pending_batches.append,
        on_item_result=lambda item, result: item_results.append(
            (item.title, result.created, len(result.errors))
        ),
    )

    assert len(pending_batches) == 1
    assert {item.title for item in pending_batches[0]} == {
        "Progress fail title",
        "Progress ok title",
    }
    assert len(item_results) == 2
    assert ("Progress fail title", 0, 1) in item_results
    assert ("Progress ok title", 1, 0) in item_results


def test_collect_articles_fetches_different_publishers_in_parallel(news_connection):
    """서로 다른 언론사의 본문 요청은 동시에 진행하고 DB 저장은 완료한다."""

    connection = news_connection
    items = (
        CanonicalRssEntry(
            id=hashlib.sha256(b"https://example.com/edaily-parallel").hexdigest(),
            publisher="edaily",
            url="https://example.com/edaily-parallel",
            title="Edaily parallel",
            author=None,
            summary=None,
            published_at=datetime(2026, 6, 10, 21, 0, tzinfo=SEOUL),
        ),
        CanonicalRssEntry(
            id=hashlib.sha256(b"https://example.com/newspim-parallel").hexdigest(),
            publisher="newspim",
            url="https://example.com/newspim-parallel",
            title="Newspim parallel",
            author=None,
            summary=None,
            published_at=datetime(2026, 6, 10, 21, 1, tzinfo=SEOUL),
        ),
    )
    for item in items:
        create_rss_item(connection, item)

    barrier = threading.Barrier(2, timeout=2)

    def fetch_html(url):
        barrier.wait()
        if "edaily" in url:
            return _edaily_html("Edaily body")
        return "<div id='news-contents'><p>Newspim body</p></div>"

    result = collect_articles(
        connection,
        fetch_html=fetch_html,
        article_parsers={
            "edaily": ARTICLE_PARSERS["edaily"],
            "newspim": ARTICLE_PARSERS["newspim"],
        },
    )

    assert result == OperationResult(processed=2, created=2, skipped=0)
    assert connection.execute("SELECT count(*) FROM articles").fetchone() == (2,)


@pytest.mark.parametrize(
    ("extra_args", "expected_limit"),
    [([], 100), (["--limit", "7"], 7), (["--all"], None)],
)
def test_collect_articles_cli_runs_preserved_collection_flow(
    monkeypatch,
    extra_args,
    expected_limit,
):
    """본문 수집 명령은 보존된 진행 표시 수집 흐름을 실행한다."""

    from typer.testing import CliRunner

    from modules.news import main as news_main

    calls = []

    def collect_with_progress(dsn, limit):
        calls.append((dsn, limit))

    monkeypatch.setattr(
        news_main,
        "_collect_articles_with_progress",
        collect_with_progress,
    )
    dsn = "postgresql://example/news"

    result = CliRunner().invoke(
        news_main.app,
        ["collect-articles", "--dsn", dsn, *extra_args],
    )

    assert result.exit_code == 0
    assert calls == [(dsn, expected_limit)]


def test_collect_articles_all_processes_every_pending_item(news_connection):
    """limit=None이면 기본 100개 제한 없이 모든 미수집 항목을 처리한다."""

    connection = news_connection
    entries = [
        _edaily_entry(
            f"https://www.edaily.co.kr/news/all-{index}",
            f"All title {index}",
        )
        for index in range(105)
    ]
    collect_rss(
        connection,
        sources=(_EDAILY_SOURCE,),
        feed_loader=lambda url: SimpleNamespace(entries=entries, bozo=False),
    )

    result = collect_articles(
        connection,
        limit=None,
        fetch_html=lambda url: _edaily_html("All body text"),
    )

    assert result == OperationResult(processed=105, created=105, skipped=0)
    assert connection.execute("SELECT count(*) FROM articles").fetchone() == (105,)


def test_collect_articles_excludes_metadata_only_investing_source(news_connection):
    """본문 parser가 없는 investing.com 항목은 수집 대상에서 제외된다."""

    connection = news_connection
    raw_entry = {
        "author": "Investing.com",
        "link": "https://kr.investing.com/news/login-walled",
        "published": "2026-06-10 21:00:00",
        "published_parsed": _published_parsed(),
        "title": "Investing title",
    }
    collect_rss(
        connection,
        sources=(DEFAULT_FEED_SOURCES[0],),
        feed_loader=lambda url: SimpleNamespace(entries=[raw_entry], bozo=False),
    )

    result = collect_articles(
        connection,
        fetch_html=lambda url: pytest.fail(f"must not fetch: {url}"),
    )

    assert result == OperationResult(processed=0, created=0, skipped=0)
    assert connection.execute("SELECT count(*) FROM rss_items").fetchone() == (1,)
    assert connection.execute("SELECT count(*) FROM articles").fetchone() == (0,)


def test_collect_rss_merges_categories_for_duplicate_article_urls(news_connection):
    """같은 기사가 여러 피드에 있으면 행은 하나만 두고 카테고리를 합친다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    sources = (
        FeedSource(
            "etoday",
            "https://example.com/economy.xml",
            parser,
            feed_category="경제",
        ),
        FeedSource(
            "etoday",
            "https://example.com/market.xml",
            parser,
            feed_category="마켓",
        ),
    )

    def load_feed(url):
        source_category = "거시경제" if url.endswith("economy.xml") else "증권"
        return SimpleNamespace(
            entries=[
                {
                    "author": "기자",
                    "link": "https://www.etoday.co.kr/news/view/duplicate",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "요약",
                    "tags": [{"term": source_category}],
                    "title": "Duplicate article",
                }
            ],
            bozo=False,
        )

    result = collect_rss(connection, sources=sources, feed_loader=load_feed)
    item = read_rss_item(
        connection,
        hashlib.sha256(b"https://www.etoday.co.kr/news/view/duplicate").hexdigest(),
    )

    assert result == OperationResult(processed=2, created=1, skipped=1)
    assert item is not None
    assert item.feed_categories == ("경제", "마켓")
    assert item.source_categories == ("거시경제", "증권")


def test_collect_rss_skips_entries_missing_required_fields(news_connection):
    """link 등 필수 필드가 없는 항목은 건너뛰고 나머지 항목과 소스는 계속 수집한다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    source = FeedSource("etoday", "https://example.com/feed.xml", parser)

    def load_feed(url):
        return SimpleNamespace(
            entries=[
                {
                    "author": "기자",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "link 없는 항목",
                    "title": "Broken entry",
                },
                {
                    "author": "기자",
                    "link": "https://www.etoday.co.kr/news/view/valid",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "정상 항목",
                    "title": "Valid entry",
                },
            ],
            bozo=False,
        )

    result = collect_rss(connection, sources=(source,), feed_loader=load_feed)

    assert result.processed == 2
    assert result.created == 1
    assert len(result.errors) == 1
    assert "etoday" in result.errors[0]


def test_collect_rss_skips_a_feed_that_returns_http_error(news_connection):
    """429 등 한 피드의 HTTP 오류는 전체 수집을 중단하지 않고 그 피드만 건너뛴다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    rate_limited = FeedSource(
        "etoday", "https://example.com/rate-limited.xml", parser, feed_category="경제"
    )
    healthy = FeedSource(
        "etoday", "https://example.com/ok.xml", parser, feed_category="마켓"
    )

    def load_feed(url):
        if "rate-limited" in url:
            request = httpx.Request("GET", url)
            raise httpx.HTTPStatusError(
                "rate limited",
                request=request,
                response=httpx.Response(429, request=request),
            )
        return SimpleNamespace(
            entries=[
                {
                    "author": "기자",
                    "link": "https://www.etoday.co.kr/news/view/healthy",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "요약",
                    "title": "정상 기사",
                }
            ],
            bozo=False,
        )

    # Must not raise even though one feed returns 429.
    result = collect_rss(
        connection, sources=(rate_limited, healthy), feed_loader=load_feed
    )

    assert result.created == 1  # the healthy feed was still stored
    assert any("HTTP 429" in message for message in result.errors)


def test_feed_cooldown_minutes_escalates():
    """연속 429 횟수가 늘수록 쿨다운이 5→15→30분으로 점증하고 30분에서 멈춘다."""

    assert feed_cooldown_minutes(1) == 5
    assert feed_cooldown_minutes(2) == 15
    assert feed_cooldown_minutes(3) == 30
    assert feed_cooldown_minutes(4) == 30


def test_register_feed_rate_limit_escalates_cooldown(news_connection):
    """연속 429를 등록하면 streak이 늘고 회피 종료 시각이 점점 미뤄진다."""

    connection = news_connection
    url = "https://example.com/throttled.xml"

    first = register_feed_rate_limit(connection, url=url, publisher="etoday")
    second = register_feed_rate_limit(connection, url=url, publisher="etoday")
    third = register_feed_rate_limit(connection, url=url, publisher="etoday")

    assert (first.streak, second.streak, third.streak) == (1, 2, 3)
    assert feed_cooldown_minutes(first.streak) == 5
    assert feed_cooldown_minutes(second.streak) == 15
    assert feed_cooldown_minutes(third.streak) == 30
    # 더 긴 쿨다운일수록 회피 종료 시각이 더 뒤로 간다.
    assert first.skip_until < second.skip_until < third.skip_until
    now_db = connection.execute("SELECT now()").fetchone()[0]
    assert third.skip_until > now_db


def test_collect_rss_sets_incremental_cooldown_on_429(news_connection):
    """429를 만나면 그 피드에 연속 1회·5분 쿨다운을 설정하고 안내를 남긴다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    url = "https://example.com/rate-limited.xml"
    source = FeedSource("etoday", url, parser, feed_category="경제")

    def load_feed(_url):
        request = httpx.Request("GET", _url)
        raise httpx.HTTPStatusError(
            "rate limited",
            request=request,
            response=httpx.Response(429, request=request),
        )

    result = collect_rss(connection, sources=(source,), feed_loader=load_feed)

    assert any(
        "HTTP 429" in message and "5분 쿨다운" in message and "연속 1회" in message
        for message in result.errors
    )
    active = list_active_feed_cooldowns(connection)
    assert url in active
    assert active[url].streak == 1


def test_collect_rss_skips_a_feed_in_active_cooldown(news_connection):
    """활성 쿨다운인 피드는 fetch하지 않고 건너뛰며 streak은 그대로 둔다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    cooled_url = "https://example.com/cooled.xml"
    register_feed_rate_limit(connection, url=cooled_url, publisher="etoday")

    cooled = FeedSource("etoday", cooled_url, parser, feed_category="경제")
    healthy = FeedSource(
        "etoday", "https://example.com/ok.xml", parser, feed_category="마켓"
    )

    def load_feed(url):
        # 쿨다운 중인 피드는 절대 fetch되어선 안 된다.
        assert "cooled" not in url, "쿨다운 피드를 fetch하면 안 됨"
        return SimpleNamespace(
            entries=[
                {
                    "author": "기자",
                    "link": "https://www.etoday.co.kr/news/view/ok",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "요약",
                    "title": "정상 기사",
                }
            ],
            bozo=False,
        )

    result = collect_rss(
        connection, sources=(cooled, healthy), feed_loader=load_feed
    )

    assert result.created == 1  # the healthy feed was still stored
    assert any("쿨다운" in message for message in result.errors)
    # 건너뛰기만 했으므로 연속 횟수는 1회 그대로다.
    assert list_active_feed_cooldowns(connection)[cooled_url].streak == 1


def test_collect_rss_clears_cooldown_after_successful_collection(news_connection):
    """만료된 쿨다운 피드를 정상 수집하면 연속 429 횟수가 초기화된다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    url = "https://example.com/recovered.xml"
    # 이미 만료된 쿨다운 행을 직접 넣어 이번 회차에 다시 fetch되게 한다.
    connection.execute(
        """
        INSERT INTO rss_feed_cooldowns (url, publisher, streak, skip_until)
        VALUES (%s, 'etoday', 2, now() - interval '1 minute')
        """,
        [url],
    )
    source = FeedSource("etoday", url, parser, feed_category="경제")

    def load_feed(_url):
        return SimpleNamespace(
            entries=[
                {
                    "author": "기자",
                    "link": "https://www.etoday.co.kr/news/view/recovered",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "요약",
                    "title": "복구된 기사",
                }
            ],
            bozo=False,
        )

    result = collect_rss(connection, sources=(source,), feed_loader=load_feed)

    assert result.created == 1
    remaining = connection.execute(
        "SELECT count(*) FROM rss_feed_cooldowns WHERE url = %s", [url]
    ).fetchone()[0]
    assert remaining == 0


def test_collect_rss_reports_each_source_result_in_order(news_connection):
    """소스 하나의 수집이 끝날 때마다 소스별 결과가 순서대로 콜백에 전달된다."""

    connection = news_connection
    parser = PARSERS["etoday"]
    sources = (
        FeedSource(
            "etoday",
            "https://example.com/economy.xml",
            parser,
            feed_category="경제",
        ),
        FeedSource(
            "etoday",
            "https://example.com/market.xml",
            parser,
            feed_category="마켓",
        ),
    )

    def load_feed(url):
        return SimpleNamespace(
            entries=[
                {
                    "author": "기자",
                    "link": "https://www.etoday.co.kr/news/view/progress",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "요약",
                    "title": "Progress article",
                }
            ],
            bozo=False,
        )

    reported: list[tuple[FeedSource, OperationResult]] = []
    result = collect_rss(
        connection,
        sources=sources,
        feed_loader=load_feed,
        on_source_result=lambda source, source_result: reported.append(
            (source, source_result)
        ),
    )

    assert result == OperationResult(processed=2, created=1, skipped=1)
    assert reported == [
        (sources[0], OperationResult(processed=1, created=1, skipped=0)),
        (sources[1], OperationResult(processed=1, created=0, skipped=1)),
    ]


def test_collect_rss_fetches_different_publishers_in_parallel(news_connection):
    """서로 다른 언론사의 RSS 요청은 동시에 진행하고 결과는 정상 저장한다."""

    connection = news_connection
    sources = (
        FeedSource("edaily", "https://example.com/edaily.xml", PARSERS["edaily"]),
        FeedSource("etoday", "https://example.com/etoday.xml", PARSERS["etoday"]),
    )
    barrier = threading.Barrier(2, timeout=2)

    def load_feed(url):
        barrier.wait()
        publisher = "edaily" if "edaily" in url else "etoday"
        return SimpleNamespace(
            entries=[
                {
                    "author": publisher,
                    "link": f"https://example.com/{publisher}-article",
                    "published": "Wed, 10 Jun 2026 21:00:00 +0900",
                    "summary": "요약",
                    "title": f"{publisher} article",
                }
            ],
            bozo=False,
        )

    result = collect_rss(connection, sources=sources, feed_loader=load_feed)

    assert result == OperationResult(processed=2, created=2, skipped=0)
    assert connection.execute("SELECT count(*) FROM rss_items").fetchone() == (2,)


def test_recorded_operation_persists_success_and_failure(news_connection):
    """각 단계의 성공·실패 상태와 오류 메시지가 실행 이력에 남는다."""

    connection = news_connection

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
