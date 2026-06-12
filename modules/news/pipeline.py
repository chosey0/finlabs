"""뉴스 수집과 분석 단계를 독립적으로 실행하는 애플리케이션 서비스를 제공한다."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from html.parser import HTMLParser
from typing import Any, Protocol

import duckdb
import feedparser
import httpx

from .db.sql import (
    finish_pipeline_run,
    insert_article,
    insert_rss_item,
    list_articles_without_current_analysis,
    list_rss_items_without_articles,
    start_pipeline_run,
    upsert_article_analysis,
)
from .rss.parsers import PARSERS, BaseRssParser
from .schema.article import ArticleAnalysis, CanonicalArticle, make_content_hash


ANALYZER_VERSION = "basic-stats-v1"
DEFAULT_USER_AGENT = "FinLabsNewsCollector/0.1"


class FeedLoader(Protocol):
    """feedparser와 테스트 대역이 공유하는 RSS 로더 계약이다."""

    def __call__(self, url: str) -> Any:
        """RSS URL을 읽어 ``entries``를 가진 결과를 반환한다."""


@dataclass(frozen=True, slots=True)
class FeedSource:
    """RSS URL과 해당 언론사 파서를 묶은 수집 설정이다."""

    publisher: str
    url: str
    parser: BaseRssParser
    domain_category: str | None = None
    feed_category: str | None = None


@dataclass(frozen=True, slots=True)
class OperationResult:
    """한 파이프라인 단계가 처리한 항목 수를 요약한다."""

    processed: int
    created: int
    skipped: int


HANKYUNG_CATEGORY_FEEDS = {
    "증권": "https://www.hankyung.com/feed/finance",
    "경제": "https://www.hankyung.com/feed/economy",
    "부동산": "https://www.hankyung.com/feed/realestate",
    "IT": "https://www.hankyung.com/feed/it",
    "정치": "https://www.hankyung.com/feed/politics",
    "국제": "https://www.hankyung.com/feed/international",
    "사회": "https://www.hankyung.com/feed/society",
    "생활": "https://www.hankyung.com/feed/life",
    "오피니언": "https://www.hankyung.com/feed/opinion",
    "스포츠": "https://www.hankyung.com/feed/sports",
    "연예": "https://www.hankyung.com/feed/entertainment",
}
SEDAILY_CATEGORY_FEEDS = {
    "증권": "https://www.sedaily.com/rss/finance",
    "부동산": "https://www.sedaily.com/rss/realestate",
    "경제": "https://www.sedaily.com/rss/economy",
    "정치": "https://www.sedaily.com/rss/politics",
    "사회": "https://www.sedaily.com/rss/society",
    "국제": "https://www.sedaily.com/rss/international",
    "IT": "https://www.sedaily.com/rss/it",
    "오피니언": "https://www.sedaily.com/rss/opinion",
    "생활": "https://www.sedaily.com/rss/life",
    "스포츠": "https://www.sedaily.com/rss/sports",
    "연예": "https://www.sedaily.com/rss/entertainment",
}


def _category_feed_sources(
    publisher: str,
    feeds: Mapping[str, str],
) -> tuple[FeedSource, ...]:
    """카테고리명과 URL 매핑을 기본 피드 소스 목록으로 변환한다."""

    parser = PARSERS[publisher]
    return tuple(
        FeedSource(
            publisher=publisher,
            url=url,
            parser=parser,
            feed_category=category,
        )
        for category, url in feeds.items()
    )


DEFAULT_FEED_SOURCES = (
    FeedSource(
        publisher="investing.com",
        url="https://kr.investing.com/rss/news.rss",
        parser=PARSERS["investing.com"],
        domain_category="금융",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_357.rss",
        PARSERS["investing.com"],
        "금융",
        "내부자거래",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_1065.rss",
        PARSERS["investing.com"],
        "금융",
        "주식시장투자아이디어",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_1064.rss",
        PARSERS["investing.com"],
        "금융",
        "SEC 공시",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_1063.rss",
        PARSERS["investing.com"],
        "금융",
        "어닝콜 스크립트",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_1062.rss",
        PARSERS["investing.com"],
        "금융",
        "실적보고서와 발표예정일",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_1061.rss",
        PARSERS["investing.com"],
        "금융",
        "애널리스트 투자의견",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_450.rss",
        PARSERS["investing.com"],
        "금융",
        "IPO",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_301.rss",
        PARSERS["investing.com"],
        "금융",
        "암호화폐",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_1.rss",
        PARSERS["investing.com"],
        "금융",
        "외환",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_285.rss",
        PARSERS["investing.com"],
        "금융",
        "많이 본 기사",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_25.rss",
        PARSERS["investing.com"],
        "금융",
        "주식 시장 뉴스",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_11.rss",
        PARSERS["investing.com"],
        "금융",
        "상품과 선물 뉴스",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_95.rss",
        PARSERS["investing.com"],
        "금융",
        "경제 지표 뉴스",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_12.rss",
        PARSERS["investing.com"],
        "금융",
        "스포츠 및 일반 뉴스",
    ),
    FeedSource(
        "investing.com",
        "https://kr.investing.com/rss/news_14.rss",
        PARSERS["investing.com"],
        "금융",
        "경제 뉴스",
    ),
    FeedSource(
        publisher="edaily",
        url="http://rss.edaily.co.kr/edaily_news.xml",
        parser=PARSERS["edaily"],
    ),
    FeedSource(
        publisher="hankyung",
        url="https://www.hankyung.com/feed/all-news",
        parser=PARSERS["hankyung"],
    ),
    *_category_feed_sources("hankyung", HANKYUNG_CATEGORY_FEEDS),
    FeedSource(
        publisher="sedaily",
        url="https://www.sedaily.com/rss/newsall",
        parser=PARSERS["sedaily"],
    ),
    *_category_feed_sources("sedaily", SEDAILY_CATEGORY_FEEDS),
    FeedSource(
        publisher="etoday",
        url="https://rss.etoday.co.kr/eto/etoday_news_all.xml",
        parser=PARSERS["etoday"],
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/finance_news.xml",
        PARSERS["etoday"],
        feed_category="금융",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/market_news.xml",
        PARSERS["etoday"],
        feed_category="마켓",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/land_news.xml",
        PARSERS["etoday"],
        feed_category="부동산",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/industry_news.xml",
        PARSERS["etoday"],
        feed_category="산업",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/economy_news.xml",
        PARSERS["etoday"],
        feed_category="경제",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/global_news.xml",
        PARSERS["etoday"],
        feed_category="국제",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/politics_news.xml",
        PARSERS["etoday"],
        feed_category="정치",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/society_news.xml",
        PARSERS["etoday"],
        feed_category="사회",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/opinion_news.xml",
        PARSERS["etoday"],
        feed_category="오피니언",
    ),
    FeedSource(
        "etoday",
        "https://rss.etoday.co.kr/eto/culture-life_news.xml",
        PARSERS["etoday"],
        feed_category="문화/라이프",
    ),
    FeedSource(
        publisher="newspim",
        url="http://rss.newspim.com/news/category/1",
        parser=PARSERS["newspim"],
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/101",
        PARSERS["newspim"],
        feed_category="정치",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/103",
        PARSERS["newspim"],
        feed_category="경제",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/102",
        PARSERS["newspim"],
        feed_category="사회",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/107",
        PARSERS["newspim"],
        feed_category="글로벌",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/106",
        PARSERS["newspim"],
        feed_category="산업",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/105",
        PARSERS["newspim"],
        feed_category="증권/금융",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/104",
        PARSERS["newspim"],
        feed_category="부동산",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/112",
        PARSERS["newspim"],
        feed_category="라이프/여행",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/110",
        PARSERS["newspim"],
        feed_category="문화/연예",
    ),
    FeedSource(
        "newspim",
        "http://rss.newspim.com/news/category/111",
        PARSERS["newspim"],
        feed_category="스포츠",
    ),
)


def load_feed(url: str) -> Any:
    """RSS 원문을 HTTP로 가져온 뒤 feedparser 항목으로 변환한다."""

    response = httpx.get(
        url,
        follow_redirects=True,
        timeout=30.0,
        headers={"User-Agent": DEFAULT_USER_AGENT},
    )
    response.raise_for_status()
    return feedparser.parse(response.content)


def collect_rss(
    connection: duckdb.DuckDBPyConnection,
    *,
    sources: Iterable[FeedSource] = DEFAULT_FEED_SOURCES,
    feed_loader: FeedLoader = load_feed,
    on_source_result: Callable[[FeedSource, OperationResult], None] | None = None,
) -> OperationResult:
    """RSS 피드를 파싱해 표준 항목을 중복 없이 저장한다.

    ``on_source_result``를 주면 소스 하나의 수집이 끝날 때마다 해당 소스의
    결과를 전달하므로 호출자가 진행 상황과 소스별 집계를 표시할 수 있다.
    """

    processed = 0
    created = 0
    for source in sources:
        feed = feed_loader(source.url)
        entries = getattr(feed, "entries", None)
        if entries is None:
            raise RuntimeError(f"RSS loader returned no entries for {source.publisher}")
        if getattr(feed, "bozo", False) and not entries:
            error = getattr(feed, "bozo_exception", "invalid feed")
            raise RuntimeError(f"failed to parse {source.publisher} RSS: {error}")
        source_processed = 0
        source_created = 0
        for raw_entry in entries:
            source_processed += 1
            item = source.parser.parse(raw_entry)
            item = replace(
                item,
                domain_category=source.domain_category,
                feed_categories=(source.feed_category,) if source.feed_category else (),
            )
            source_created += int(insert_rss_item(connection, item))
        processed += source_processed
        created += source_created
        if on_source_result is not None:
            on_source_result(
                source,
                OperationResult(
                    processed=source_processed,
                    created=source_created,
                    skipped=source_processed - source_created,
                ),
            )
    return OperationResult(
        processed=processed,
        created=created,
        skipped=processed - created,
    )


def collect_articles(
    connection: duckdb.DuckDBPyConnection,
    *,
    limit: int = 100,
    fetch_html: Callable[[str], str] | None = None,
) -> OperationResult:
    """본문이 없는 RSS 항목의 HTML을 가져와 정규화된 텍스트로 저장한다."""

    if fetch_html is None:
        with httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:

            def fetch_with_client(url: str) -> str:
                response = client.get(url)
                response.raise_for_status()
                return response.text

            return collect_articles(
                connection,
                limit=limit,
                fetch_html=fetch_with_client,
            )

    pending = list_rss_items_without_articles(connection, limit=limit)
    created = 0
    for item in pending:
        content = extract_article_text(fetch_html(item.url))
        article = CanonicalArticle(
            rss_item_id=item.id,
            content=content,
            content_hash=make_content_hash(content),
        )
        created += int(insert_article(connection, article))
    return OperationResult(
        processed=len(pending),
        created=created,
        skipped=len(pending) - created,
    )


def analyze_articles(
    connection: duckdb.DuckDBPyConnection,
    *,
    limit: int = 100,
    analyzer_version: str = ANALYZER_VERSION,
) -> OperationResult:
    """미분석 기사에 결정적 문자 수와 단어 수 통계를 저장한다."""

    pending = list_articles_without_current_analysis(
        connection,
        analyzer_version=analyzer_version,
        limit=limit,
    )
    for article in pending:
        upsert_article_analysis(
            connection,
            ArticleAnalysis(
                rss_item_id=article.rss_item_id,
                analyzer_version=analyzer_version,
                content_hash=article.content_hash,
                character_count=len(article.content),
                word_count=len(article.content.split()),
            ),
        )
    return OperationResult(
        processed=len(pending),
        created=len(pending),
        skipped=0,
    )


def run_recorded_operation(
    connection: duckdb.DuckDBPyConnection,
    *,
    command: str,
    parameters: dict[str, object],
    operation: Callable[[], OperationResult],
) -> OperationResult:
    """파이프라인 단계를 실행하고 성공·실패 이력을 항상 완료 상태로 기록한다."""

    run_id = start_pipeline_run(
        connection,
        command=command,
        parameters=parameters,
    )
    try:
        result = operation()
    except Exception as error:
        finish_pipeline_run(
            connection,
            run_id,
            status="failed",
            error_message=_safe_error_message(error),
        )
        raise
    finish_pipeline_run(
        connection,
        run_id,
        status="succeeded",
        processed_count=result.processed,
        created_count=result.created,
        skipped_count=result.skipped,
    )
    return result


def parse_feed_source(value: str) -> FeedSource:
    """``publisher=url`` CLI 값을 검증된 RSS 소스로 변환한다."""

    publisher, separator, url = value.partition("=")
    publisher = publisher.strip()
    url = url.strip()
    if not separator or not publisher or not url:
        raise ValueError("feed must use publisher=https://example.com/rss format")
    parser = PARSERS.get(publisher)
    if parser is None:
        supported = ", ".join(sorted(PARSERS))
        raise ValueError(
            f"unsupported publisher {publisher!r}; choose one of: {supported}"
        )
    if not url.startswith(("http://", "https://")):
        raise ValueError("feed URL must use HTTP or HTTPS")
    return FeedSource(publisher=publisher, url=url, parser=parser)


class _ArticleTextExtractor(HTMLParser):
    """HTML에서 스크립트와 스타일을 제외한 가시 텍스트를 추출한다."""

    _ignored_tags = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() in self._ignored_tags:
            self._ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self._ignored_depth:
            self.parts.append(data)


def extract_article_text(html: str) -> str:
    """HTML 문서를 공백이 정규화된 비어 있지 않은 본문 텍스트로 변환한다."""

    extractor = _ArticleTextExtractor()
    extractor.feed(html)
    content = re.sub(r"\s+", " ", " ".join(extractor.parts)).strip()
    if not content:
        raise ValueError("article page contains no visible text")
    return content


def _safe_error_message(error: Exception) -> str:
    """실행 이력에 저장할 제한된 길이의 오류 문자열을 반환한다."""

    return f"{type(error).__name__}: {error}"[:2000]
