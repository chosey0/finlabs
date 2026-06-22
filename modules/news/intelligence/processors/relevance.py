"""Dependency-free deterministic direct-mention relevance suggestion."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from modules.domain.news_intelligence import CatalogAlias

RULE_VERSION = "literal-direct-mention-v1"


@dataclass(frozen=True, slots=True)
class DirectMentionEvidence:
    alias_id: str
    term: str
    field: str
    start: int
    end: int
    matched_text: str


@dataclass(frozen=True, slots=True)
class RelevanceSuggestion:
    value: str
    rule_version: str
    evidence: tuple[DirectMentionEvidence, ...]


def suggest_direct_mention(
    *,
    title: str,
    description: str,
    aliases: tuple[CatalogAlias, ...],
) -> RelevanceSuggestion:
    evidence: list[DirectMentionEvidence] = []
    for field, original in (("title", title), ("description", description)):
        normalized_text = _normalize(original)
        folded_text = normalized_text.casefold()
        for alias in sorted(aliases, key=lambda item: item.alias_id):
            normalized_term = _normalize(alias.term)
            if not normalized_term:
                continue
            start = folded_text.find(normalized_term.casefold())
            if start < 0:
                continue
            end = start + len(normalized_term)
            evidence.append(
                DirectMentionEvidence(
                    alias_id=alias.alias_id,
                    term=normalized_term,
                    field=field,
                    start=start,
                    end=end,
                    matched_text=normalized_text[start:end],
                )
            )
    ordered = tuple(
        sorted(evidence, key=lambda item: (item.field, item.start, item.alias_id))
    )
    return RelevanceSuggestion(
        value="relevant" if ordered else "unresolved",
        rule_version=RULE_VERSION,
        evidence=ordered,
    )


def _normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())
