"""종목 마스터와 별칭 사전 기반의 결정적 종목 entity 추출기를 제공한다.

PLAN 5절: 종목명→티커 매핑은 종목 마스터(정식명)와 별칭 사전(약칭,
옛 사명, 영문명)을 단일 어휘집으로 합쳐 수행한다. 긴 이름을 먼저
매칭하고 소비된 구간을 제외해, "한화솔루션" 기사에서 "한화"가 함께
추출되는 오탐을 방지한다.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

NAME_MATCH_CONFIDENCE = 1.0
ALIAS_MATCH_CONFIDENCE = 0.9
MIN_NAME_LENGTH = 2

# 별칭 사전 시드. 키는 KIS 종목 마스터의 정식 한글명이며, 마스터에 없는
# 키는 무시된다. 전면적인 별칭 사전 구축은 PLAN 5.1절의 독립 작업이다.
DEFAULT_STOCK_ALIASES: dict[str, tuple[str, ...]] = {
    "삼성전자": ("삼전",),
    "SK하이닉스": ("하이닉스",),
    "NAVER": ("네이버",),
}


@dataclass(frozen=True, slots=True)
class LexiconEntry:
    """어휘집의 표면형 하나와 그 정규화 결과를 나타낸다."""

    surface: str
    canonical_name: str
    ticker: str
    confidence: float


@dataclass(frozen=True, slots=True)
class StockMatch:
    """본문에서 발견된 종목 하나의 매칭 결과를 나타낸다."""

    canonical_name: str
    ticker: str
    confidence: float


def build_symbol_lexicon(
    symbols: Sequence[tuple[str, str]],
    *,
    aliases: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[LexiconEntry, ...]:
    """(종목명, 티커) 목록과 별칭 사전을 긴 이름 우선 어휘집으로 만든다."""

    alias_map = DEFAULT_STOCK_ALIASES if aliases is None else aliases
    entries: dict[str, LexiconEntry] = {}
    for name, ticker in symbols:
        canonical = name.strip()
        code = ticker.strip()
        if len(canonical) < MIN_NAME_LENGTH or not code:
            continue
        entries.setdefault(
            canonical,
            LexiconEntry(
                surface=canonical,
                canonical_name=canonical,
                ticker=code,
                confidence=NAME_MATCH_CONFIDENCE,
            ),
        )
        for alias in alias_map.get(canonical, ()):
            surface = alias.strip()
            if len(surface) < MIN_NAME_LENGTH:
                continue
            entries.setdefault(
                surface,
                LexiconEntry(
                    surface=surface,
                    canonical_name=canonical,
                    ticker=code,
                    confidence=ALIAS_MATCH_CONFIDENCE,
                ),
            )
    return tuple(
        sorted(entries.values(), key=lambda entry: (-len(entry.surface), entry.surface))
    )


def match_stock_entities(
    text: str,
    lexicon: Sequence[LexiconEntry],
) -> tuple[StockMatch, ...]:
    """본문에서 종목을 찾아 티커별 최고 신뢰도 매칭을 반환한다."""

    consumed: list[tuple[int, int]] = []
    matches: dict[str, StockMatch] = {}
    for entry in lexicon:
        start = 0
        while True:
            index = text.find(entry.surface, start)
            if index < 0:
                break
            end = index + len(entry.surface)
            start = end
            if _overlaps(consumed, index, end):
                continue
            consumed.append((index, end))
            existing = matches.get(entry.ticker)
            if existing is None or entry.confidence > existing.confidence:
                matches[entry.ticker] = StockMatch(
                    canonical_name=entry.canonical_name,
                    ticker=entry.ticker,
                    confidence=entry.confidence,
                )
    return tuple(
        sorted(matches.values(), key=lambda match: (-match.confidence, match.ticker))
    )


def _overlaps(spans: Sequence[tuple[int, int]], start: int, end: int) -> bool:
    return any(start < span_end and end > span_start for span_start, span_end in spans)
