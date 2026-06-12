"""서울경제 RSS 항목을 표준 뉴스 스키마로 변환한다."""

from __future__ import annotations

from typing import Any, Mapping

from .base import BaseRssParser, CanonicalRssEntry, optional_text


class SedailyRssParser(BaseRssParser):
    """서울경제 feedparser 항목을 검증하고 표준 구조로 정규화한다."""

    publisher = "sedaily"

    def parse(self, data: Mapping[str, Any]) -> CanonicalRssEntry:
        """서울경제 RSS 항목을 표준 항목으로 변환한다."""

        return self.build_entry(data, summary=optional_text(data.get("summary")))
