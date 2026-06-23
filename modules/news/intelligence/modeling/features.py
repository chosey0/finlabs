"""Point-in-time feature assembly for surge-ranking samples.

Only information available at the feature cutoff (t0) is used: news text, the
security's market, calendar position, whether the anchor was rolled forward
(an after-hours signal), and the pre-anchor microstructure scalars (beta and the
turnover z-score). The label-side cross-sectional standardization is deliberately
*not* a feature, since it depends on the day's outcomes.

The text embedder is a protocol so a real Korean sentence encoder can replace the
dependency-free hashing default without touching the rest of the pipeline.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from modules.news.intelligence.modeling.dataset import SurgeSample

_MARKETS = ("KOSPI", "KOSDAQ")
_ADJUSTMENTS = ("none", "rolled_to_next_session")


class TextEmbedder(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed(self, text: str) -> list[float]: ...


@dataclass(frozen=True, slots=True)
class FeatureMatrix:
    feature_names: tuple[str, ...]
    rows: tuple[tuple[float, ...], ...]
    regression_target: tuple[float | None, ...]
    surge_label: tuple[int, ...]


class HashingTextEmbedder:
    """Dependency-free character n-gram hashing embedder (L2-normalized).

    Deterministic and fast; a stand-in for a real sentence encoder so the pipeline
    runs without downloading a model. Not meant to be competitive on its own.
    """

    def __init__(self, dimension: int = 64, ngram_range: tuple[int, int] = (2, 4)) -> None:
        if dimension <= 0:
            raise ValueError("dimension must be positive")
        low, high = ngram_range
        if not 1 <= low <= high:
            raise ValueError("ngram_range must satisfy 1 <= low <= high")
        self._dimension = dimension
        self._ngram_range = ngram_range

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        normalized = unicodedata.normalize("NFKC", text).casefold().strip()
        if not normalized:
            return vector
        low, high = self._ngram_range
        for size in range(low, high + 1):
            for index in range(len(normalized) - size + 1):
                token = normalized[index : index + size]
                digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
                bucket = int.from_bytes(digest, "big") % self._dimension
                sign = 1.0 if digest[0] & 1 else -1.0
                vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]


def build_features(
    rows: Sequence[SurgeSample], embedder: TextEmbedder
) -> FeatureMatrix:
    """Assemble the feature matrix and aligned targets for the given rows."""

    feature_names = _feature_names(embedder.dimension)
    matrix: list[tuple[float, ...]] = []
    regression_target: list[float | None] = []
    surge_label: list[int] = []
    for row in rows:
        matrix.append(tuple(_row_features(row, embedder)))
        regression_target.append(row.abnormal_return_std)
        surge_label.append(row.surge_label)
    return FeatureMatrix(
        feature_names=feature_names,
        rows=tuple(matrix),
        regression_target=tuple(regression_target),
        surge_label=tuple(surge_label),
    )


def _feature_names(text_dimension: int) -> tuple[str, ...]:
    names = [
        "turnover_zscore",
        "beta",
        "minute_sin",
        "minute_cos",
        "weekday",
        *(f"market_{market}" for market in _MARKETS),
        *(f"anchor_{adjustment}" for adjustment in _ADJUSTMENTS),
    ]
    names.extend(f"text_{index}" for index in range(text_dimension))
    return tuple(names)


def _row_features(row: SurgeSample, embedder: TextEmbedder) -> list[float]:
    minute_of_day = row.anchor.hour * 60 + row.anchor.minute
    angle = 2 * math.pi * minute_of_day / (24 * 60)
    features = [
        row.turnover_zscore if row.turnover_zscore is not None else 0.0,
        row.beta if row.beta is not None else 1.0,
        math.sin(angle),
        math.cos(angle),
        float(row.anchor.weekday()),
        *(1.0 if row.market == market else 0.0 for market in _MARKETS),
        *(1.0 if row.anchor_adjustment == value else 0.0 for value in _ADJUSTMENTS),
    ]
    features.extend(embedder.embed(row.text))
    return features
