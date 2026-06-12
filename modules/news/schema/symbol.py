"""뉴스 파이프라인이 사용하는 국내 종목 마스터 모델을 정의한다."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class NewsSymbol:
    """KIS 종목 마스터를 뉴스 DB에 저장하기 위한 정규화 모델이다."""

    market: str
    symbol: str
    standard_code: str = ""
    realtime_symbol: str = ""
    korean_name: str = ""
    english_name: str = ""
    security_type: str = ""
    currency: str = "KRW"
    exchange_id: str = ""
    exchange_code: str = ""
    exchange_name: str = ""
    country_code: str = "KR"
    listed_date: str = ""
    base_price: int | None = None
    lot_size: int | None = None
    raw_source: str = ""
    raw: dict[str, str] = field(default_factory=dict)
    downloaded_at: str = ""
