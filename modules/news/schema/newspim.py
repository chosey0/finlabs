"""뉴스핌 RSS 항목을 표준 뉴스 스키마로 변환한다."""

from __future__ import annotations

from typing import Any, Mapping

from .base import BaseRssParser, CanonicalRssEntry, optional_text


class NewspimRssParser(BaseRssParser):
    """뉴스핌 feedparser 항목을 검증하고 표준 구조로 정규화한다."""

    publisher = "newspim"

    def parse(self, data: Mapping[str, Any]) -> CanonicalRssEntry:
        """뉴스핌 RSS 항목의 요약을 포함해 표준 항목으로 변환한다."""

        return self.build_entry(data, summary=optional_text(data.get("summary")))


# articles 본문 CSS Selector = id="news-contents" > p
