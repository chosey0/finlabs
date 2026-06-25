"""뉴스 수집과 분석 단계를 독립적으로 실행하는 애플리케이션 서비스를 제공한다."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import Any, Protocol

import feedparser
import httpx
import psycopg

from .articles.parsers import ARTICLE_PARSERS, BaseArticleParser
from .db.sql import (
    finish_pipeline_run,
    insert_article,
    insert_rss_item,
    list_articles_requiring_entity_extraction,
    list_articles_without_current_analysis,
    list_domestic_symbol_names,
    list_rss_items_requiring_article_parse,
    replace_article_entities,
    start_pipeline_run,
    upsert_article_analysis,
)
from .entities import build_symbol_lexicon, match_stock_entities
from .rss.models import CanonicalRssEntry
from .rss.parsers import PARSERS, BaseRssParser
from .schema.article import ArticleAnalysis, CanonicalArticle, make_content_hash
from .schema.entity import ArticleEntity


ANALYZER_VERSION = "basic-stats-v1"
ENTITY_EXTRACTOR_VERSION = "symbol-master-v1"
DEFAULT_USER_AGENT = "FinLabsNewsCollector/0.1"
MAX_PUBLISHER_WORKERS = 8


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
    errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _RssFetchResult:
    index: int
    source: FeedSource
    processed: int
    items: tuple[CanonicalRssEntry, ...]
    invalid_count: int = 0
    feed_error: str | None = None


@dataclass(frozen=True, slots=True)
class _ArticleFetchResult:
    index: int
    item: CanonicalRssEntry
    article: CanonicalArticle | None = None
    error_message: str | None = None


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
DONGA_CATEGORY_FEEDS = {
    "정치": "https://rss.donga.com/politics.xml",
    "사회": "https://rss.donga.com/national.xml",
    "경제": "https://rss.donga.com/economy.xml",
    "국제": "https://rss.donga.com/international.xml",
    "과학": "https://rss.donga.com/science.xml",
    "연예": "https://rss.donga.com/culture.xml",
    "스포츠": "https://rss.donga.com/sports.xml",
    "건강": "https://rss.donga.com/health.xml",
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
        url="https://rss.newspim.com/news/category/1",
        parser=PARSERS["newspim"],
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/101",
        PARSERS["newspim"],
        feed_category="정치",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/103",
        PARSERS["newspim"],
        feed_category="경제",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/102",
        PARSERS["newspim"],
        feed_category="사회",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/107",
        PARSERS["newspim"],
        feed_category="글로벌",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/106",
        PARSERS["newspim"],
        feed_category="산업",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/105",
        PARSERS["newspim"],
        feed_category="증권/금융",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/104",
        PARSERS["newspim"],
        feed_category="부동산",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/112",
        PARSERS["newspim"],
        feed_category="라이프/여행",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/110",
        PARSERS["newspim"],
        feed_category="문화/연예",
    ),
    FeedSource(
        "newspim",
        "https://rss.newspim.com/news/category/111",
        PARSERS["newspim"],
        feed_category="스포츠",
    ),
    FeedSource(
        publisher="donga",
        url="https://rss.donga.com/total.xml",
        parser=PARSERS["donga"],
    ),
    *_category_feed_sources("donga", DONGA_CATEGORY_FEEDS),
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


def _group_sources_by_publisher(
    sources: tuple[FeedSource, ...],
) -> tuple[tuple[tuple[int, FeedSource], ...], ...]:
    groups: dict[str, list[tuple[int, FeedSource]]] = {}
    for index, source in enumerate(sources):
        groups.setdefault(source.publisher, []).append((index, source))
    return tuple(tuple(group) for group in groups.values())


def _fetch_rss_publisher(
    sources: tuple[tuple[int, FeedSource], ...],
    feed_loader: FeedLoader,
) -> tuple[_RssFetchResult, ...]:
    results: list[_RssFetchResult] = []
    for index, source in sources:
        feed = feed_loader(source.url)
        entries = getattr(feed, "entries", None) or []
        if getattr(feed, "bozo", False) and not entries:
            error = getattr(feed, "bozo_exception", "invalid feed")
            results.append(
                _RssFetchResult(
                    index=index,
                    source=source,
                    processed=0,
                    items=(),
                    feed_error=f"{source.publisher}: {error}",
                )
            )
            continue

        items: list[CanonicalRssEntry] = []
        invalid_count = 0
        for raw_entry in entries:
            try:
                item = source.parser.parse(raw_entry)
            except (TypeError, ValueError):
                invalid_count += 1
                continue
            items.append(
                replace(
                    item,
                    domain_category=source.domain_category,
                    feed_categories=(
                        (source.feed_category,) if source.feed_category else ()
                    ),
                )
            )
        results.append(
            _RssFetchResult(
                index=index,
                source=source,
                processed=len(entries),
                items=tuple(items),
                invalid_count=invalid_count,
            )
        )
    return tuple(results)


def collect_rss(
    connection: psycopg.Connection,
    *,
    sources: Iterable[FeedSource] = DEFAULT_FEED_SOURCES,
    feed_loader: FeedLoader = load_feed,
    on_source_result: Callable[[FeedSource, OperationResult], None] | None = None,
) -> OperationResult:
    """RSS 피드를 파싱해 표준 항목을 중복 없이 저장한다.

    ``on_source_result``를 주면 소스 하나의 수집이 끝날 때마다 해당 소스의
    결과를 전달하므로 호출자가 진행 상황과 소스별 집계를 표시할 수 있다.
    """

    source_tuple = tuple(sources)
    publisher_groups = _group_sources_by_publisher(source_tuple)
    if not publisher_groups:
        return OperationResult(processed=0, created=0, skipped=0)

    processed = 0
    created = 0
    indexed_errors: list[tuple[int, str]] = []
    worker_count = min(MAX_PUBLISHER_WORKERS, len(publisher_groups))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="finlabs-rss",
    ) as executor:
        futures = [
            executor.submit(_fetch_rss_publisher, group, feed_loader)
            for group in publisher_groups
        ]
        for future in as_completed(futures):
            for fetched in future.result():
                source_created = sum(
                    int(insert_rss_item(connection, item)) for item in fetched.items
                )
                source_errors: list[str] = []
                if fetched.feed_error is not None:
                    source_errors.append(fetched.feed_error)
                if fetched.invalid_count:
                    source_errors.append(
                        f"{fetched.source.publisher}: {fetched.invalid_count}개 "
                        "항목이 필수 필드 누락으로 제외됨"
                    )
                for message in source_errors:
                    indexed_errors.append((fetched.index, message))
                processed += fetched.processed
                created += source_created
                if on_source_result is not None:
                    on_source_result(
                        fetched.source,
                        OperationResult(
                            processed=fetched.processed,
                            created=source_created,
                            skipped=fetched.processed - source_created,
                            errors=tuple(source_errors),
                        ),
                    )
    return OperationResult(
        processed=processed,
        created=created,
        skipped=processed - created,
        errors=tuple(message for _, message in sorted(indexed_errors)),
    )


def _group_articles_by_publisher(
    items: tuple[CanonicalRssEntry, ...],
) -> tuple[tuple[tuple[int, CanonicalRssEntry], ...], ...]:
    groups: dict[str, list[tuple[int, CanonicalRssEntry]]] = {}
    for index, item in enumerate(items):
        groups.setdefault(item.publisher, []).append((index, item))
    return tuple(tuple(group) for group in groups.values())


def _fetch_article_publisher(
    items: tuple[tuple[int, CanonicalRssEntry], ...],
    *,
    fetch_html: Callable[[str], str] | None,
    article_parsers: Mapping[str, BaseArticleParser],
) -> tuple[_ArticleFetchResult, ...]:
    if fetch_html is None:
        with httpx.Client(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            return _fetch_article_publisher(
                items,
                fetch_html=lambda url: client.get(url).raise_for_status().text,
                article_parsers=article_parsers,
            )

    results: list[_ArticleFetchResult] = []
    for index, item in items:
        parser = article_parsers[item.publisher]
        try:
            content = parser.parse(fetch_html(item.url))
        except (httpx.HTTPError, ValueError) as error:
            results.append(
                _ArticleFetchResult(
                    index=index,
                    item=item,
                    error_message=(
                        f"{item.publisher}: {item.url} — {_safe_error_message(error)}"
                    ),
                )
            )
            continue
        results.append(
            _ArticleFetchResult(
                index=index,
                item=item,
                article=CanonicalArticle(
                    rss_item_id=item.id,
                    content=content,
                    content_hash=make_content_hash(content),
                    parser_version=parser.version,
                ),
            )
        )
    return tuple(results)


def collect_articles(
    connection: psycopg.Connection,
    *,
    limit: int | None = 100,
    fetch_html: Callable[[str], str] | None = None,
    article_parsers: Mapping[str, BaseArticleParser] = ARTICLE_PARSERS,
    on_pending: Callable[[tuple[CanonicalRssEntry, ...]], None] | None = None,
    on_item_result: Callable[[CanonicalRssEntry, OperationResult], None] | None = None,
) -> OperationResult:
    """본문이 없거나 parser 버전이 지난 RSS 항목을 정제해 저장한다.

    ``on_pending``은 수집 대상이 확정된 직후 한 번 호출되고,
    ``on_item_result``는 기사 하나가 끝날 때마다 해당 기사의 결과를
    전달하므로 호출자가 진행 상황과 기사 제목을 표시할 수 있다.
    """

    pending = list_rss_items_requiring_article_parse(
        connection,
        parser_versions={
            publisher: parser.version for publisher, parser in article_parsers.items()
        },
        limit=limit,
    )
    if on_pending is not None:
        on_pending(pending)
    publisher_groups = _group_articles_by_publisher(pending)
    if not publisher_groups:
        return OperationResult(processed=0, created=0, skipped=0)

    created = 0
    indexed_errors: list[tuple[int, str]] = []
    worker_count = min(MAX_PUBLISHER_WORKERS, len(publisher_groups))
    with ThreadPoolExecutor(
        max_workers=worker_count,
        thread_name_prefix="finlabs-articles",
    ) as executor:
        futures = [
            executor.submit(
                _fetch_article_publisher,
                group,
                fetch_html=fetch_html,
                article_parsers=article_parsers,
            )
            for group in publisher_groups
        ]
        for future in as_completed(futures):
            for fetched in future.result():
                if fetched.error_message is not None:
                    indexed_errors.append((fetched.index, fetched.error_message))
                    if on_item_result is not None:
                        on_item_result(
                            fetched.item,
                            OperationResult(
                                processed=1,
                                created=0,
                                skipped=1,
                                errors=(fetched.error_message,),
                            ),
                        )
                    continue
                if fetched.article is None:
                    raise RuntimeError("article fetch result is missing article data")
                item_created = int(insert_article(connection, fetched.article))
                created += item_created
                if on_item_result is not None:
                    on_item_result(
                        fetched.item,
                        OperationResult(
                            processed=1,
                            created=item_created,
                            skipped=1 - item_created,
                        ),
                    )
    return OperationResult(
        processed=len(pending),
        created=created,
        skipped=len(pending) - created,
        errors=tuple(message for _, message in sorted(indexed_errors)),
    )


def analyze_articles(
    connection: psycopg.Connection,
    *,
    limit: int | None = 100,
    analyzer_version: str = ANALYZER_VERSION,
    on_pending: Callable[
        [tuple[tuple[CanonicalArticle, str], ...]], None
    ]
    | None = None,
    on_item_result: Callable[[CanonicalArticle, str, OperationResult], None]
    | None = None,
) -> OperationResult:
    """미분석 기사에 결정적 문자 수와 단어 수 통계를 저장한다."""

    pending = list_articles_without_current_analysis(
        connection,
        analyzer_version=analyzer_version,
        limit=limit,
    )
    if on_pending is not None:
        on_pending(pending)
    for article, title in pending:
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
        if on_item_result is not None:
            on_item_result(
                article,
                title,
                OperationResult(processed=1, created=1, skipped=0),
            )
    return OperationResult(
        processed=len(pending),
        created=len(pending),
        skipped=0,
    )


def extract_entities(
    connection: psycopg.Connection,
    *,
    limit: int | None = 100,
    extractor_version: str = ENTITY_EXTRACTOR_VERSION,
    aliases: Mapping[str, tuple[str, ...]] | None = None,
    on_pending: Callable[
        [tuple[tuple[CanonicalArticle, str], ...]], None
    ]
    | None = None,
    on_item_result: Callable[[CanonicalArticle, str, OperationResult], None]
    | None = None,
) -> OperationResult:
    """종목 마스터 어휘집으로 기사별 종목 entity를 추출해 저장한다.

    추출은 결정적이며, 추출기 버전이나 본문 해시가 바뀐 기사만
    재처리한다. created는 entity가 1개 이상 발견된 기사 수이다.
    """

    lexicon = build_symbol_lexicon(
        list_domestic_symbol_names(connection),
        aliases=aliases,
    )
    if not lexicon:
        raise ValueError(
            "domestic symbol master is empty; run update-symbols before extract-entities"
        )
    pending = list_articles_requiring_entity_extraction(
        connection,
        extractor_version=extractor_version,
        limit=limit,
    )
    if on_pending is not None:
        on_pending(pending)
    created = 0
    for article, title in pending:
        matches = match_stock_entities(f"{title}\n{article.content}", lexicon)
        entities = tuple(
            ArticleEntity(
                rss_item_id=article.rss_item_id,
                entity_type="stock",
                entity_name=match.canonical_name,
                ticker=match.ticker,
                confidence=match.confidence,
            )
            for match in matches
        )
        replace_article_entities(
            connection,
            rss_item_id=article.rss_item_id,
            content_hash=article.content_hash,
            extractor_version=extractor_version,
            entities=entities,
        )
        item_created = int(bool(entities))
        created += item_created
        if on_item_result is not None:
            on_item_result(
                article,
                title,
                OperationResult(
                    processed=1,
                    created=item_created,
                    skipped=1 - item_created,
                ),
            )
    return OperationResult(
        processed=len(pending),
        created=created,
        skipped=len(pending) - created,
    )


def run_recorded_operation(
    connection: psycopg.Connection,
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


def _safe_error_message(error: Exception) -> str:
    """실행 이력에 저장할 제한된 길이의 오류 문자열을 반환한다."""

    return f"{type(error).__name__}: {error}"[:2000]
