"""네이버 뉴스 검색의 공개 불변 결과 모델이다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class NaverNewsArticle:
    """네이버 뉴스 검색 결과 한 건을 정규화한 값 객체다."""

    title: str
    description: str
    published_at: datetime
    original_url: str | None
    naver_url: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        if self.published_at.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")
        if self.original_url is not None and not self.original_url.strip():
            raise ValueError("original_url must be None or non-empty")
        if not self.naver_url.strip():
            raise ValueError("naver_url must not be empty")

    @property
    def canonical_url(self) -> str:
        """중복 제거에 사용할 원문 우선 URL을 반환한다."""

        return self.original_url or self.naver_url
