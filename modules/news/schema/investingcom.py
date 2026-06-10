"""Investing.com RSS 항목을 표준 뉴스 스키마로 변환한다."""

from __future__ import annotations

from typing import Any, Mapping

from .base import BaseRssParser, CanonicalRssEntry


class InvestingComRssParser(BaseRssParser):
    """Investing.com feedparser 항목을 검증하고 표준 구조로 정규화한다."""

    publisher = "investing.com"

    def parse(self, data: Mapping[str, Any]) -> CanonicalRssEntry:
        """요약이 없는 Investing.com RSS 항목을 표준 항목으로 변환한다."""

        return self.build_entry(data, summary=None)


# article 본문 내용 CSS selector = id="article" > p
