"""기사에서 추출한 entity의 표준 모델을 정의한다."""

from __future__ import annotations

from dataclasses import dataclass

ENTITY_TYPES: tuple[str, ...] = ("stock", "company", "industry", "keyword")


@dataclass(frozen=True, slots=True)
class ArticleEntity:
    """기사 한 건에서 추출된 entity 하나를 나타낸다 (PLAN 5.2절)."""

    rss_item_id: str
    entity_type: str
    entity_name: str
    ticker: str | None
    confidence: float

    def __post_init__(self) -> None:
        if not self.rss_item_id.strip():
            raise ValueError("rss_item_id must not be empty")
        if self.entity_type not in ENTITY_TYPES:
            raise ValueError(f"entity_type must be one of: {', '.join(ENTITY_TYPES)}")
        if not self.entity_name.strip():
            raise ValueError("entity_name must not be empty")
        if self.ticker is not None and not self.ticker.strip():
            raise ValueError("ticker must not be blank")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
