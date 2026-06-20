"""재사용 가능한 네이버 뉴스 검색 클라이언트의 공개 경계를 정의한다."""

from __future__ import annotations

import html
import re
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import httpx

from .errors import (
    NaverNewsAuthenticationError,
    NaverNewsError,
    NaverNewsIncompleteSearchError,
    NaverNewsMalformedResponseError,
    NaverNewsPermissionError,
    NaverNewsRateLimitError,
    NaverNewsUpstreamError,
    NaverNewsValidationError,
)
from .models import NaverNewsArticle

NAVER_NEWS_SEARCH_URL = "https://openapi.naver.com/v1/search/news.json"
NAVER_MAX_DISPLAY = 100
NAVER_MAX_START = 1000
_HIGHLIGHT_TAG = re.compile(r"</?b\s*>", re.IGNORECASE)


class HttpResponse(Protocol):
    """테스트 대역과 HTTP 응답이 공유하는 최소 계약이다."""

    status_code: int
    headers: Mapping[str, str]

    def json(self) -> Any:
        """JSON 응답 본문을 반환한다."""


class HttpTransport(Protocol):
    """동기 HTTP transport의 최소 계약이다."""

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> HttpResponse:
        """GET 요청을 실행한다."""


class NaverNewsClient:
    """키워드와 날짜로 네이버 뉴스 결과를 조회한다."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        transport: HttpTransport | None = None,
        max_attempts: int = 3,
        backoff_seconds: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not client_id.strip():
            raise NaverNewsValidationError("client_id must not be empty")
        if not client_secret.strip():
            raise NaverNewsValidationError("client_secret must not be empty")
        if max_attempts < 1:
            raise NaverNewsValidationError("max_attempts must be at least 1")
        if backoff_seconds < 0:
            raise NaverNewsValidationError("backoff_seconds must not be negative")

        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport or httpx.Client(timeout=30.0)
        self._owns_transport = transport is None
        self._max_attempts = max_attempts
        self._backoff_seconds = backoff_seconds
        self._sleep = sleep

    def search(self, keyword: str, published_on: date) -> tuple[NaverNewsArticle, ...]:
        """지정 날짜의 검색 결과를 완전성 보장과 함께 반환한다."""

        normalized_keyword = _validate_search_input(keyword, published_on)
        articles_by_url: dict[str, NaverNewsArticle] = {}
        start = 1

        while True:
            payload = self._request_page(keyword=normalized_keyword, start=start)
            items, total = _parse_page(payload, expected_start=start)

            for item in items:
                article = _parse_article(item)
                item_date = article.published_at.date()
                if item_date == published_on:
                    _keep_preferred_duplicate(articles_by_url, article)

            exhausted = start + len(items) > total
            if exhausted:
                break
            if len(items) < NAVER_MAX_DISPLAY:
                raise NaverNewsMalformedResponseError(
                    "Naver response ended before its total result count"
                )

            if start == NAVER_MAX_START:
                raise NaverNewsIncompleteSearchError(
                    "Naver pagination limit prevents a complete date search"
                )
            start = min(start + NAVER_MAX_DISPLAY, NAVER_MAX_START)

        return tuple(
            sorted(
                articles_by_url.values(),
                key=lambda article: (
                    -article.published_at.timestamp(),
                    article.canonical_url,
                ),
            )
        )

    def close(self) -> None:
        """클라이언트가 생성한 기본 HTTP transport를 닫는다."""

        if self._owns_transport and isinstance(self._transport, httpx.Client):
            self._transport.close()

    def __enter__(self) -> NaverNewsClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request_page(self, *, keyword: str, start: int) -> Mapping[str, Any]:
        headers = {
            "X-Naver-Client-Id": self._client_id,
            "X-Naver-Client-Secret": self._client_secret,
        }
        params: Mapping[str, object] = {
            "query": keyword,
            "display": NAVER_MAX_DISPLAY,
            "start": start,
            "sort": "date",
        }

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._transport.get(
                    NAVER_NEWS_SEARCH_URL,
                    params=params,
                    headers=headers,
                )
            except httpx.HTTPError:
                if attempt >= self._max_attempts:
                    raise NaverNewsUpstreamError(
                        "Naver news request failed after bounded retries"
                    ) from None
                self._sleep(_backoff_delay(attempt, self._backoff_seconds))
                continue

            status_error = _status_error(response.status_code)
            if status_error is not None:
                retryable = response.status_code == 429 or response.status_code >= 500
                if retryable and attempt < self._max_attempts:
                    self._sleep(
                        _response_retry_delay(
                            response.status_code,
                            response.headers,
                            attempt,
                            self._backoff_seconds,
                        )
                    )
                    continue
                raise status_error

            try:
                payload = response.json()
            except (TypeError, ValueError) as error:
                raise NaverNewsMalformedResponseError(
                    "Naver news response was not valid JSON"
                ) from error
            if not isinstance(payload, Mapping):
                raise NaverNewsMalformedResponseError(
                    "Naver news response must be a JSON object"
                )
            return payload

        raise RuntimeError("unreachable")


def _validate_search_input(keyword: str, published_on: date) -> str:
    if not isinstance(keyword, str) or not keyword.strip():
        raise NaverNewsValidationError("keyword must not be empty")
    if not isinstance(published_on, date) or isinstance(published_on, datetime):
        raise NaverNewsValidationError("published_on must be a datetime.date")
    return keyword.strip()


def _keep_preferred_duplicate(
    articles_by_url: dict[str, NaverNewsArticle],
    candidate: NaverNewsArticle,
) -> None:
    existing = articles_by_url.get(candidate.canonical_url)
    if existing is None or _duplicate_preference(candidate) > _duplicate_preference(
        existing
    ):
        articles_by_url[candidate.canonical_url] = candidate


def _duplicate_preference(article: NaverNewsArticle) -> tuple[float, str, str, str]:
    return (
        article.published_at.timestamp(),
        article.title,
        article.description,
        article.naver_url,
    )


def _parse_page(
    payload: Mapping[str, Any],
    *,
    expected_start: int,
) -> tuple[list[Mapping[str, Any]], int]:
    total = payload.get("total")
    response_start = payload.get("start")
    display = payload.get("display")
    items = payload.get("items")
    if not isinstance(total, int) or total < 0:
        raise NaverNewsMalformedResponseError("response total must be non-negative")
    if response_start != expected_start:
        raise NaverNewsMalformedResponseError("response start did not match the request")
    if not isinstance(display, int) or display < 0 or display > NAVER_MAX_DISPLAY:
        raise NaverNewsMalformedResponseError("response display was invalid")
    if not isinstance(items, list) or any(not isinstance(item, Mapping) for item in items):
        raise NaverNewsMalformedResponseError("response items must be JSON objects")
    if len(items) > NAVER_MAX_DISPLAY:
        raise NaverNewsMalformedResponseError("response contained too many items")
    return items, total


def _parse_article(item: Mapping[str, Any]) -> NaverNewsArticle:
    title = _required_text(item, "title")
    description = _required_text(item, "description", allow_empty=True)
    naver_url = _required_text(item, "link")
    original_url = item.get("originallink")
    if original_url is not None and not isinstance(original_url, str):
        raise NaverNewsMalformedResponseError("originallink must be a string")
    normalized_original_url = original_url.strip() if original_url else ""

    published_at = _parse_pub_date(_required_text(item, "pubDate"))
    try:
        return NaverNewsArticle(
            title=_normalize_highlight(title),
            description=_normalize_highlight(description),
            published_at=published_at,
            original_url=normalized_original_url or None,
            naver_url=naver_url.strip(),
        )
    except ValueError as error:
        raise NaverNewsMalformedResponseError(
            "Naver news item contained invalid values"
        ) from error


def _required_text(
    item: Mapping[str, Any],
    field: str,
    *,
    allow_empty: bool = False,
) -> str:
    value = item.get(field)
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise NaverNewsMalformedResponseError(
            f"Naver news item field '{field}' must be a string"
        )
    return value


def _parse_pub_date(value: str) -> datetime:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError) as error:
        raise NaverNewsMalformedResponseError("pubDate was invalid") from error
    if parsed.tzinfo is None:
        raise NaverNewsMalformedResponseError("pubDate must include a UTC offset")
    return parsed


def _normalize_highlight(value: str) -> str:
    return html.unescape(_HIGHLIGHT_TAG.sub("", value)).strip()


def _status_error(status_code: int) -> NaverNewsError | None:
    if status_code < 400:
        return None
    if status_code == 401:
        return NaverNewsAuthenticationError("Naver rejected the client credentials")
    if status_code == 403:
        return NaverNewsPermissionError(
            "Naver denied access to the news search API"
        )
    if status_code == 429:
        return NaverNewsRateLimitError("Naver news search rate limit was exceeded")
    if status_code >= 500:
        return NaverNewsUpstreamError("Naver news service failed after bounded retries")
    return NaverNewsUpstreamError(
        f"Naver news request failed with HTTP {status_code}"
    )


def _response_retry_delay(
    status_code: int,
    headers: Mapping[str, str],
    attempt: int,
    backoff_seconds: float,
) -> float:
    retry_after = headers.get("Retry-After") if status_code == 429 else None
    if retry_after:
        parsed_retry_after = _parse_retry_after(retry_after)
        if parsed_retry_after is not None:
            return parsed_retry_after
    return _backoff_delay(attempt, backoff_seconds)


def _parse_retry_after(value: str) -> float | None:
    try:
        return max(0.0, float(value))
    except ValueError:
        return None


def _backoff_delay(attempt: int, backoff_seconds: float) -> float:
    return backoff_seconds * (2 ** (attempt - 1))
