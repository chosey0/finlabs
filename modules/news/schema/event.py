"""LLM 이벤트 분류의 닫힌 taxonomy와 분석 결과 DTO를 정의한다.

PLAN 7.3절: 자유 서술 라벨은 같은 이벤트가 다른 표기로 파편화되므로
event_type을 닫힌 목록(enum)으로 강제하고, taxonomy 변경 시
``TAXONOMY_VERSION``을 올려 영향 구간을 재분류한다.
"""

from __future__ import annotations

from dataclasses import dataclass

TAXONOMY_VERSION = "v1"

EVENT_TYPE_DEFINITIONS: dict[str, str] = {
    "contract_supply": "공급·납품 계약 체결/확대",
    "order_win": "수주 (건설·방산·플랜트 등)",
    "regulatory_approval": "인허가·승인 (FDA, 식약처 등)",
    "clinical_result": "임상 결과 발표",
    "earnings": "실적 발표·전망 (서프라이즈 포함)",
    "product_launch": "신제품·신서비스 출시",
    "tech_patent": "신기술 개발·특허",
    "partnership": "제휴·협력·MOU",
    "ma_investment": "M&A·지분 투자·유치",
    "capital_change": "유상증자·감자·CB 발행",
    "policy_theme": "정부 정책·테마 편입",
    "litigation_risk": "소송·제재·악재",
    "management": "경영진·지배구조 변화",
    "market_commentary": "시황·업종 일반 기사",
    "simple_mention": "타 기업이 주인공, 단순 언급",
    "other": "위에 없는 유형",
}

EVENT_TAXONOMY: tuple[str, ...] = tuple(EVENT_TYPE_DEFINITIONS)

# 유사도 검색 대상에서 제외하는 노이즈 유형 (PLAN 7.3.2).
NOISE_EVENT_TYPES: tuple[str, ...] = ("market_commentary", "simple_mention")

SPECIFICITY_LEVELS: tuple[str, ...] = ("high", "low")


@dataclass(frozen=True, slots=True)
class ArticleEvent:
    """기사 한 건에 대한 LLM 이벤트 분류 결과를 나타낸다.

    entities는 LLM이 추출한 기업명 그대로 보존하고, tickers는 종목
    마스터 매핑 결과만 담는다 — LLM에게 티커를 직접 묻지 않는다.
    """

    rss_item_id: str
    event_type: str
    entities: tuple[str, ...]
    tickers: tuple[str, ...]
    industry: str
    specificity: str | None
    confidence: float
    reason: str
    label_model: str
    prompt_version: str
    taxonomy_version: str = TAXONOMY_VERSION

    def __post_init__(self) -> None:
        if not self.rss_item_id.strip():
            raise ValueError("rss_item_id must not be empty")
        if self.event_type not in EVENT_TAXONOMY:
            raise ValueError(
                f"event_type must be one of the taxonomy: {self.event_type!r}"
            )
        if self.specificity is not None and self.specificity not in SPECIFICITY_LEVELS:
            raise ValueError("specificity must be high, low, or None")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        if not self.label_model.strip():
            raise ValueError("label_model must not be empty")
        if not self.prompt_version.strip():
            raise ValueError("prompt_version must not be empty")
        if not self.taxonomy_version.strip():
            raise ValueError("taxonomy_version must not be empty")
