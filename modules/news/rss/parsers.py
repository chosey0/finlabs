"""언론사 RSS 항목을 표준 뉴스 모델로 변환한다."""

from __future__ import annotations

import calendar
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any, Mapping

from .models import (
    SEOUL_TIMEZONE,
    CanonicalRssEntry,
    make_rss_item_id,
)


class BaseRssParser(ABC):
    """feedparser 항목을 표준 RSS 항목으로 변환하는 파서 계약이다."""

    @abstractmethod
    def parse(self, data: Mapping[str, Any]) -> CanonicalRssEntry:
        """RSS 항목 하나를 검증된 표준 항목으로 변환한다."""


@dataclass(frozen=True, slots=True)
class RssParser(BaseRssParser):
    """언론사명과 요약 사용 여부로 동작하는 공통 RSS 파서다."""

    publisher: str
    use_summary: bool = True

    def parse(self, data: Mapping[str, Any]) -> CanonicalRssEntry:
        """공통 RSS 필드를 추출해 표준 항목으로 변환한다."""

        url = _required_text(data, "link")
        return CanonicalRssEntry(
            id=make_rss_item_id(url),
            publisher=self.publisher,
            url=url,
            title=_required_text(data, "title"),
            author=_extract_author(data),
            summary=_optional_text(data.get("summary")) if self.use_summary else None,
            published_at=_extract_published_at(data),
            source_categories=_extract_source_categories(data),
        )


PARSERS: Mapping[str, BaseRssParser] = {
    "investing.com": RssParser("investing.com", use_summary=False),
    "edaily": RssParser("edaily"),
    "etoday": RssParser("etoday"),
    "hankyung": RssParser("hankyung"),
    "newspim": RssParser("newspim"),
    "sedaily": RssParser("sedaily"),
}


def _required_text(data: Mapping[str, Any], key: str) -> str:
    """매핑에서 필수 문자열을 꺼내 공백을 제거한다."""

    value = data.get(key)
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    if not value.strip():
        raise ValueError(f"{key} must not be empty")
    return value.strip()


def _optional_text(value: Any) -> str | None:
    """선택 값을 공백이 제거된 문자열 또는 ``None``으로 정규화한다."""

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_author(data: Mapping[str, Any]) -> str | None:
    """feedparser 작성자 필드에서 우선순위에 따라 작성자명을 추출한다."""

    author_detail = data.get("author_detail")
    if isinstance(author_detail, Mapping):
        name = _optional_text(author_detail.get("name"))
        if name is not None:
            return name
    return _optional_text(data.get("author"))


def _extract_source_categories(data: Mapping[str, Any]) -> tuple[str, ...]:
    """feedparser의 category/tags 값을 가공하지 않은 이름으로 추출한다."""

    categories: list[str] = []
    category = _optional_text(data.get("category"))
    if category is not None:
        categories.append(category)
    tags = data.get("tags")
    if isinstance(tags, (list, tuple)):
        for tag in tags:
            if isinstance(tag, Mapping):
                term = _optional_text(tag.get("term"))
                if term is not None:
                    categories.append(term)
    return tuple(dict.fromkeys(categories))


def _extract_published_at(data: Mapping[str, Any]) -> datetime:
    """RSS 발행 시각을 추출해 서울 기준 datetime으로 정규화한다."""

    published = _optional_text(data.get("published"))
    if published is not None:
        value = _parse_published_text(published)
        if value is not None:
            return value.replace(tzinfo=value.tzinfo or SEOUL_TIMEZONE).astimezone(
                SEOUL_TIMEZONE
            )

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
