"""수집된 기사 본문과 기본 분석 결과의 표준 모델을 정의한다."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass


def make_content_hash(content: str) -> str:
    """정규화된 기사 본문의 SHA-256 해시를 반환한다."""

    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CanonicalArticle:
    """RSS 항목에 연결된 검증된 기사 본문을 나타낸다."""

    rss_item_id: str
    content: str
    content_hash: str

    def __post_init__(self) -> None:
        if not self.rss_item_id.strip():
            raise ValueError("rss_item_id must not be empty")
        if not self.content.strip():
            raise ValueError("content must not be empty")
        if self.content_hash != make_content_hash(self.content):
            raise ValueError("content_hash must be the SHA-256 hash of content")


@dataclass(frozen=True, slots=True)
class ArticleAnalysis:
    """기사 본문에 대한 결정적 기본 통계 분석 결과를 나타낸다."""

    rss_item_id: str
    analyzer_version: str
    content_hash: str
    character_count: int
    word_count: int

    def __post_init__(self) -> None:
        if not self.rss_item_id.strip():
            raise ValueError("rss_item_id must not be empty")
        if not self.analyzer_version.strip():
            raise ValueError("analyzer_version must not be empty")
        if len(self.content_hash) != 64:
            raise ValueError("content_hash must be a SHA-256 digest")
        if self.character_count < 0 or self.word_count < 0:
            raise ValueError("analysis counts must not be negative")
