"""뉴스 수집과 분석 단계를 독립적으로 실행하는 애플리케이션 서비스를 제공한다."""

from __future__ import annotations

import errno
import fcntl
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
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
from .schema.article import ArticleAnalysis, CanonicalArticle, make_content_hash
from .schema.base import BaseRssParser
from .schema.etoday import EtodayRssParser
from .schema.investingcom import InvestingComRssParser
from .schema.newspim import NewspimRssParser


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


@dataclass(frozen=True, slots=True)
class OperationResult:
    """한 파이프라인 단계가 처리한 항목 수를 요약한다."""

    processed: int
    created: int
    skipped: int


PARSERS: Mapping[str, BaseRssParser] = {
    "investing.com": InvestingComRssParser(),
    "etoday": EtodayRssParser(),
    "newspim": NewspimRssParser(),
}
DEFAULT_FEED_SOURCES = (
    FeedSource(
        publisher="investing.com",
        url="https://kr.investing.com/rss/news.rss",
        parser=PARSERS["investing.com"],
    ),
    FeedSource(
        publisher="etoday",
        url="https://rss.etoday.co.kr/eto/etoday_news_all.xml",
        parser=PARSERS["etoday"],
    ),
    FeedSource(
        publisher="newspim",
        url="http://rss.newspim.com/news/category/1",
        parser=PARSERS["newspim"],
    ),
)


def collect_rss(
    connection: duckdb.DuckDBPyConnection,
    *,
    sources: Iterable[FeedSource] = DEFAULT_FEED_SOURCES,
    feed_loader: FeedLoader = feedparser.parse,
) -> OperationResult:
    """RSS 피드를 파싱해 표준 항목을 중복 없이 저장한다."""

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
        for raw_entry in entries:
            processed += 1
            item = source.parser.parse(raw_entry)
            created += int(insert_rss_item(connection, item))
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


@contextmanager
def single_writer_lock(database_path: str | Path):
    """한 데이터베이스에 하나의 CLI 파이프라인만 접근하도록 파일 잠금을 건다."""

    path = Path(database_path).expanduser()
    lock_path = path.with_suffix(f"{path.suffix}.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise RuntimeError(
                f"another news pipeline process is using {path}"
            ) from error
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


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
