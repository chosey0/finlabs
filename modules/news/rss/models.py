"""뉴스 파이프라인의 표준 RSS 데이터 모델을 정의한다."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


SEOUL_TIMEZONE = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class CanonicalRssEntry:
    """데이터베이스 적재 전에 검증된 언론사 중립 RSS 항목을 나타낸다."""

    id: str
    publisher: str
    url: str
    title: str
    author: str | None
    summary: str | None
    published_at: datetime
    domain_category: str | None = None
    feed_categories: tuple[str, ...] = ()
    source_categories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """필수값, URL, 시간대, URL 기반 ID의 유효성을 검증한다."""

        _require_text("id", self.id)
        _require_text("publisher", self.publisher)
        _require_url("url", self.url)
        _require_text("title", self.title)
        _require_optional_text("author", self.author)
        _require_optional_text("summary", self.summary)
        _require_optional_text("domain_category", self.domain_category)
        _require_text_tuple("feed_categories", self.feed_categories)
        _require_text_tuple("source_categories", self.source_categories)
        object.__setattr__(
            self,
            "feed_categories",
            _unique_texts(self.feed_categories),
        )
        object.__setattr__(
            self,
            "source_categories",
            _unique_texts(self.source_categories),
        )
        if not isinstance(self.published_at, datetime):
            raise TypeError("published_at must be a datetime")
        if self.published_at.utcoffset() is None:
            raise ValueError("published_at must include timezone information")
        object.__setattr__(
            self,
            "published_at",
            self.published_at.astimezone(SEOUL_TIMEZONE),
        )
        if self.id != make_rss_item_id(self.url):
            raise ValueError("id must be the SHA-256 hash of url")


def make_rss_item_id(url: str) -> str:
    """기사 URL을 SHA-256으로 변환한 중복 방지 ID를 반환한다."""

    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def _require_text(field_name: str, value: object) -> None:
    """값이 비어 있지 않은 문자열인지 검증한다."""

    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    if not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_optional_text(field_name: str, value: object) -> None:
    """선택 값이 존재할 경우 비어 있지 않은 문자열인지 검증한다."""

    if value is not None:
        _require_text(field_name, value)


def _require_text_tuple(field_name: str, value: object) -> None:
    """카테고리 목록이 비어 있지 않은 문자열의 tuple인지 검증한다."""

    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be a tuple")
    for item in value:
        _require_text(field_name, item)


def _unique_texts(values: Any) -> tuple[str, ...]:
    """문자열 목록의 공백과 중복을 제거하되 입력 순서를 유지한다."""

    return tuple(dict.fromkeys(str(value).strip() for value in values))


def _require_url(field_name: str, value: object) -> None:
    """값이 완전한 HTTP 또는 HTTPS URL인지 검증한다."""

    _require_text(field_name, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an HTTP(S) URL")
