"""언론사별 RSS를 공통 구조로 변환하기 위한 모델과 도구를 정의한다."""

from __future__ import annotations

import calendar
import hashlib
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, ClassVar, Mapping
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

    def __post_init__(self) -> None:
        """필수값, URL, 시간대, URL 기반 ID의 유효성을 검증한다."""

        _require_text("id", self.id)
        _require_text("publisher", self.publisher)
        _require_url("url", self.url)
        _require_text("title", self.title)
        _require_optional_text("author", self.author)
        _require_optional_text("summary", self.summary)
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


class BaseRssParser(ABC):
    """언론사별 feedparser 데이터를 표준 RSS 항목으로 변환하는 기반 클래스다."""

    publisher: ClassVar[str]

    @abstractmethod
    def parse(self, data: Mapping[str, Any]) -> CanonicalRssEntry:
        """언론사 RSS 항목 하나를 검증된 표준 RSS 항목으로 변환한다."""

        pass

    def build_entry(
        self,
        data: Mapping[str, Any],
        *,
        summary: str | None,
    ) -> CanonicalRssEntry:
        """언론사 RSS 데이터에서 공통 필드를 추출해 표준 항목을 생성한다."""

        url = required_text(data, "link")
        return CanonicalRssEntry(
            id=make_rss_item_id(url),
            publisher=self.publisher,
            url=url,
            title=required_text(data, "title"),
            author=extract_author(data),
            summary=summary,
            published_at=extract_published_at(data),
        )


def make_rss_item_id(url: str) -> str:
    """기사 URL을 SHA-256으로 변환한 중복 방지 ID를 반환한다."""

    return hashlib.sha256(url.encode("utf-8")).hexdigest()


def required_text(data: Mapping[str, Any], key: str) -> str:
    """매핑에서 필수 문자열을 꺼내 공백을 제거한 값으로 반환한다."""

    value = data.get(key)
    _require_text(key, value)
    return value.strip()


def optional_text(value: Any) -> str | None:
    """선택 값을 공백이 제거된 문자열 또는 ``None``으로 정규화한다."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def extract_author(data: Mapping[str, Any]) -> str | None:
    """feedparser 작성자 필드에서 우선순위에 따라 작성자명을 추출한다."""

    author_detail = data.get("author_detail")
    if isinstance(author_detail, Mapping):
        name = optional_text(author_detail.get("name"))
        if name is not None:
            return name
    return optional_text(data.get("author"))


def extract_published_at(data: Mapping[str, Any]) -> datetime:
    """RSS 발행 시각을 추출해 서울 기준 datetime으로 정규화한다."""

    published = optional_text(data.get("published"))
    if published is not None:
        value = _parse_published_text(published)
        if value is not None:
            return value.replace(
                tzinfo=value.tzinfo or SEOUL_TIMEZONE
            ).astimezone(SEOUL_TIMEZONE)

    parsed = data.get("published_parsed")
    if isinstance(parsed, time.struct_time):
        return datetime.fromtimestamp(
            calendar.timegm(parsed),
            tz=UTC,
        ).astimezone(SEOUL_TIMEZONE)

    raise ValueError("published must contain a supported datetime")


def _parse_published_text(published: str) -> datetime | None:
    """RSS 원문 시각을 RFC 2822 또는 ISO 8601 datetime으로 파싱한다."""

    try:
        return parsedate_to_datetime(published)
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(published)
        except ValueError:
            return None


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


def _require_url(field_name: str, value: object) -> None:
    """값이 완전한 HTTP 또는 HTTPS URL인지 검증한다."""

    _require_text(field_name, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{field_name} must be an HTTP(S) URL")
