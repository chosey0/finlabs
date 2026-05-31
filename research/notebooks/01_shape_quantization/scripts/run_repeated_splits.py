#!/usr/bin/env python3
"""Run repeated Phase 1B shape-token + range-bucket split experiments.

This script is a CLI extraction of the authoritative notebook logic in
``02_phase_1b_shape_token_plus_range_bucket.ipynb``.  It keeps the same Phase 1B
representation:

    shape_token  = VQ-VAE token learned from 4D price-shape features
    range_bucket = train-quantile volatility bucket
    final rep    = (shape_token, range_bucket)

After successful runs, ``scripts/collect_metrics.py`` is invoked to refresh
``summaries/summary.csv``. Existing run directories are never overwritten.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from math import log2
from pathlib import Path
from typing import Iterable, Literal, Sequence


def find_repo_root(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "kis_cli").is_dir() and (candidate / "research").is_dir():
            return candidate
    raise RuntimeError("FinLabs repository root를 찾지 못했습니다.")


SCRIPT_DIR = Path(__file__).resolve().parent
PHASE_DIR = SCRIPT_DIR.parent
REPO_ROOT = find_repo_root(SCRIPT_DIR)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import torch
    from sklearn.cluster import KMeans
except ImportError as exc:  # pragma: no cover - environment dependent
    raise RuntimeError(
        "Phase 1B repeated runner는 optional tokenizer dependency, matplotlib, scikit-learn이 필요합니다. "
        "먼저 `uv sync --extra tokenizers`를 실행하세요."
    ) from exc

from kis_cli.storage.warehouse import default_warehouse_file  # noqa: E402
from research.tokenizers.data import CandleBar, filter_by_min_volume, load_candles  # noqa: E402
from research.tokenizers.model import VQVAE, VQVAEConfig  # noqa: E402
from research.tokenizers.train import TrainConfig, train  # noqa: E402

SplitFamily = Literal["random", "vol_strat", "vol_holdout", "stress"]

DEFAULT_SYMBOL_UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "TSLA",
    "AMZN",
    "META",
    "GOOGL",
    "AMD",
    "INTC",
    "RKLB",
    "AVGO",
    "NFLX",
    "PLTR",
    "MU",
    "SOXX",
    "QQQ",
    "QCOM",
    "MRVL",
]
DEFAULT_RANGE_BUCKET_QUANTILES = [0.20, 0.40, 0.60, 0.80, 0.95]
DEFAULT_RANGE_BUCKET_LABELS = [
    "very_low",
    "low",
    "normal",
    "high",
    "very_high",
    "extreme",
]
FEATURE_NAMES = [
    "signed_body_ratio",
    "upper_ratio",
    "lower_ratio",
    "body_center_location",
]


@dataclass(frozen=True, slots=True)
class PriceShapeFeature:
    signed_body_ratio: float
    upper_ratio: float
    lower_ratio: float
    body_center_location: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (
            self.signed_body_ratio,
            self.upper_ratio,
            self.lower_ratio,
            self.body_center_location,
        )


@dataclass(frozen=True, slots=True)
class RangeBucketizer:
    quantiles: tuple[float, ...]
    edges: tuple[float, ...]
    labels: tuple[str, ...]

    def bucket_index(self, raw_log_range_pct: float) -> int:
        return int(
            np.searchsorted(np.array(self.edges), raw_log_range_pct, side="right")
        )


@dataclass(frozen=True, slots=True)
class VolatilityProfile:
    values: dict[str, float]
    boundaries: tuple[float, float]
    groups: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class SplitPlan:
    family: SplitFamily
    index: int
    seed: int
    train_symbols: list[str]
    val_symbols: list[str]
    test_symbols: list[str]


@dataclass(frozen=True, slots=True)
class RunnerConfig:
    market: str
    interval: str
    codebook_size: int
    max_candles_per_symbol: int
    min_candles_per_symbol: int
    min_volume: int
    train_symbol_ratio: float
    val_symbol_ratio: float
    symbol_universe: list[str]
    runs_dir: Path
    warehouse_path: Path
    latent_dim: int
    hidden_dim: int
    epochs: int
    batch_size: int
    learning_rate: float
    kmeans_n_init: int
    kmeans_max_iter: int
    range_bucket_quantiles: list[float]
    range_bucket_labels: list[str]


# ──────────────────────────────────────────────
# Notebook-extracted feature / bucket logic
# ──────────────────────────────────────────────


def set_reproducible_seed(seed: int) -> None:
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def cap_recent(
    candles: tuple[CandleBar, ...], max_items: int | None
) -> tuple[CandleBar, ...]:
    if max_items is None or len(candles) <= max_items:
        return candles
    return candles[-max_items:]


def direction(open_price: float, close_price: float) -> float:
    if close_price > open_price:
        return 1.0
    if close_price < open_price:
        return -1.0
    return 0.0


def extract_price_shape_feature(candle: CandleBar) -> PriceShapeFeature:
    total_range = max(candle.high - candle.low, 0.0)
    if total_range == 0.0:
        return PriceShapeFeature(0.0, 0.0, 0.0, 0.0)

    body_top = max(candle.open, candle.close)
    body_bottom = min(candle.open, candle.close)
    body_ratio = abs(candle.close - candle.open) / total_range
    signed_body_ratio = body_ratio * direction(candle.open, candle.close)
    upper_ratio = max(candle.high - body_top, 0.0) / total_range
    lower_ratio = max(body_bottom - candle.low, 0.0) / total_range

    body_center = (candle.open + candle.close) / 2.0
    body_center_position = (body_center - candle.low) / total_range
    body_center_location = 2.0 * body_center_position - 1.0

    return PriceShapeFeature(
        signed_body_ratio=float(signed_body_ratio),
        upper_ratio=float(upper_ratio),
        lower_ratio=float(lower_ratio),
        body_center_location=float(body_center_location),
    )


def extract_price_shape_features(
    candles: Iterable[CandleBar],
) -> tuple[PriceShapeFeature, ...]:
    return tuple(extract_price_shape_feature(candle) for candle in candles)


def feature_matrix(features: Sequence[PriceShapeFeature]) -> np.ndarray:
    return np.array([feature.as_tuple() for feature in features], dtype=np.float32)


def raw_log_range_pct(candle: CandleBar) -> float:
    reference_price = max(abs(candle.open), abs(candle.close), 1e-12)
    range_pct = max(candle.high - candle.low, 0.0) / reference_price
    return float(np.log1p(range_pct))


def fit_range_bucketizer(
    candles: Sequence[CandleBar],
    *,
    quantiles: Sequence[float],
    labels: Sequence[str],
) -> RangeBucketizer:
    values = np.array(
        [raw_log_range_pct(candle) for candle in candles], dtype=np.float64
    )
    edges = tuple(float(x) for x in np.quantile(values, quantiles))
    if len(labels) != len(edges) + 1:
        raise ValueError("number of range bucket labels must be len(edges) + 1")
    return RangeBucketizer(
        quantiles=tuple(float(x) for x in quantiles),
        edges=edges,
        labels=tuple(labels),
    )


def encode_range_buckets(
    candles: Sequence[CandleBar], bucketizer: RangeBucketizer
) -> tuple[int, ...]:
    return tuple(
        bucketizer.bucket_index(raw_log_range_pct(candle)) for candle in candles
    )


# ──────────────────────────────────────────────
# Split planning
# ──────────────────────────────────────────────


def load_symbol_candles(
    config: RunnerConfig,
) -> tuple[
    dict[str, tuple[CandleBar, ...]],
    list[str],
    list[tuple[str, int]],
    dict[str, int],
]:
    candles_by_symbol: dict[str, tuple[CandleBar, ...]] = {}
    missing_symbols: list[str] = []
    skipped_symbols: list[tuple[str, int]] = []
    volume_filtered_counts: dict[str, int] = {}

    for symbol in config.symbol_universe:
        candles = load_candles(
            config.warehouse_path,
            market=config.market,
            symbol=symbol,
            interval=config.interval,
        )
        raw_count = len(candles)
        candles = filter_by_min_volume(candles, min_volume=config.min_volume)
        volume_filtered_counts[symbol] = raw_count - len(candles)
        candles = cap_recent(candles, config.max_candles_per_symbol)
        if not candles:
            warnings.warn(
                f"{symbol}: volume filter 이후 사용할 candle을 찾지 못해 skip합니다.",
                stacklevel=2,
            )
            missing_symbols.append(symbol)
            continue
        if len(candles) < config.min_candles_per_symbol:
            warnings.warn(
                f"{symbol}: candle 수가 min_candles_per_symbol보다 적어 skip합니다 "
                f"({len(candles)} < {config.min_candles_per_symbol}).",
                stacklevel=2,
            )
            skipped_symbols.append((symbol, len(candles)))
            continue
        candles_by_symbol[symbol] = candles

    if len(candles_by_symbol) < 3:
        raise RuntimeError(
            "반복 split 실험에는 load 가능한 symbol이 최소 3개 필요합니다."
        )
    return candles_by_symbol, missing_symbols, skipped_symbols, volume_filtered_counts


def split_counts(
    total: int, train_ratio: float, val_ratio: float
) -> tuple[int, int, int]:
    if total < 3:
        raise ValueError("at least 3 symbols are required")
    train_count = int(total * train_ratio)
    val_count = int(total * val_ratio)
    train_count = max(1, train_count)
    val_count = max(1, val_count)
    if train_count + val_count >= total:
        val_count = 1
        train_count = total - 2
    test_count = total - train_count - val_count
    return train_count, val_count, test_count


def compute_volatility_profile(
    candles_by_symbol: dict[str, tuple[CandleBar, ...]],
) -> VolatilityProfile:
    values = {
        symbol: float(np.median([raw_log_range_pct(candle) for candle in candles]))
        for symbol, candles in candles_by_symbol.items()
    }
    ordered_values = np.array(
        [values[symbol] for symbol in sorted(values)], dtype=np.float64
    )
    low_boundary, high_boundary = (
        float(x) for x in np.quantile(ordered_values, [1 / 3, 2 / 3])
    )

    groups: dict[str, list[str]] = {"low": [], "medium": [], "high": []}
    for symbol, value in sorted(values.items(), key=lambda item: (item[1], item[0])):
        if value <= low_boundary:
            groups["low"].append(symbol)
        elif value <= high_boundary:
            groups["medium"].append(symbol)
        else:
            groups["high"].append(symbol)

    return VolatilityProfile(
        values=values, boundaries=(low_boundary, high_boundary), groups=groups
    )


def shuffled(items: Sequence[str], seed: int) -> list[str]:
    result = list(items)
    rng = random.Random(seed)
    rng.shuffle(result)
    return result


def plan_random_split(
    symbols: Sequence[str],
    *,
    seed: int,
    train_ratio: float,
    val_ratio: float,
) -> tuple[list[str], list[str], list[str]]:
    ordered = shuffled(symbols, seed)
    train_count, val_count, _test_count = split_counts(
        len(ordered), train_ratio, val_ratio
    )
    return (
        ordered[:train_count],
        ordered[train_count : train_count + val_count],
        ordered[train_count + val_count :],
    )


def plan_vol_strat_split(
    profile: VolatilityProfile,
    *,
    seed: int,
    train_ratio: float,
    val_ratio: float,
) -> tuple[list[str], list[str], list[str]]:
    train_symbols: list[str] = []
    val_symbols: list[str] = []
    test_symbols: list[str] = []

    for offset, group_name in enumerate(("low", "medium", "high")):
        group_symbols = profile.groups[group_name]
        if len(group_symbols) < 3:
            raise RuntimeError(
                f"vol_strat split에는 tertile별 최소 3개 symbol이 필요합니다: {group_name}={group_symbols}"
            )
        group_train, group_val, group_test = plan_random_split(
            group_symbols,
            seed=seed + offset * 10_000,
            train_ratio=train_ratio,
            val_ratio=val_ratio,
        )
        train_symbols.extend(group_train)
        val_symbols.extend(group_val)
        test_symbols.extend(group_test)

    return (
        shuffled(train_symbols, seed + 101),
        shuffled(val_symbols, seed + 102),
        shuffled(test_symbols, seed + 103),
    )


def plan_vol_holdout_split(
    profile: VolatilityProfile, *, seed: int
) -> tuple[list[str], list[str], list[str]]:
    train_symbols = profile.groups["low"] + profile.groups["medium"]
    high_symbols = shuffled(profile.groups["high"], seed)
    if len(train_symbols) < 1 or len(high_symbols) < 2:
        raise RuntimeError(
            "vol_holdout split에는 train symbol과 최소 2개 이상의 high-vol held-out symbol이 필요합니다."
        )
    val_count = max(1, len(high_symbols) // 2)
    val_count = min(val_count, len(high_symbols) - 1)
    return (
        shuffled(train_symbols, seed + 201),
        high_symbols[:val_count],
        high_symbols[val_count:],
    )


def validate_stress_symbols(
    *,
    train_symbols: Sequence[str] | None,
    val_symbols: Sequence[str] | None,
    test_symbols: Sequence[str] | None,
) -> tuple[list[str], list[str], list[str]]:
    if not train_symbols or not val_symbols or not test_symbols:
        raise ValueError(
            "stress split은 --train-symbols, --val-symbols, --test-symbols가 모두 필요합니다."
        )
    return list(train_symbols), list(val_symbols), list(test_symbols)


def make_split_plans(
    *,
    family: SplitFamily,
    n_runs: int,
    seed_start: int,
    config: RunnerConfig,
    available_symbols: Sequence[str],
    volatility_profile: VolatilityProfile | None,
    stress_train_symbols: Sequence[str] | None,
    stress_val_symbols: Sequence[str] | None,
    stress_test_symbols: Sequence[str] | None,
) -> list[SplitPlan]:
    plans: list[SplitPlan] = []
    for index in range(n_runs):
        seed = seed_start + index
        if family == "random":
            train_symbols, val_symbols, test_symbols = plan_random_split(
                available_symbols,
                seed=seed,
                train_ratio=config.train_symbol_ratio,
                val_ratio=config.val_symbol_ratio,
            )
        elif family == "vol_strat":
            if volatility_profile is None:
                raise RuntimeError(
                    "vol_strat split에는 volatility_profile이 필요합니다."
                )
            train_symbols, val_symbols, test_symbols = plan_vol_strat_split(
                volatility_profile,
                seed=seed,
                train_ratio=config.train_symbol_ratio,
                val_ratio=config.val_symbol_ratio,
            )
        elif family == "vol_holdout":
            if volatility_profile is None:
                raise RuntimeError(
                    "vol_holdout split에는 volatility_profile이 필요합니다."
                )
            train_symbols, val_symbols, test_symbols = plan_vol_holdout_split(
                volatility_profile, seed=seed
            )
        elif family == "stress":
            train_symbols, val_symbols, test_symbols = validate_stress_symbols(
                train_symbols=stress_train_symbols,
                val_symbols=stress_val_symbols,
                test_symbols=stress_test_symbols,
            )
        else:  # pragma: no cover - argparse constrains this
            raise ValueError(f"unknown split family: {family}")

        plans.append(
            SplitPlan(
                family=family,
                index=seed,
                seed=seed,
                train_symbols=train_symbols,
                val_symbols=val_symbols,
                test_symbols=test_symbols,
            )
        )
    return plans


def validate_plan_symbols(
    plan: SplitPlan, candles_by_symbol: dict[str, tuple[CandleBar, ...]]
) -> None:
    groups = {
        "train": plan.train_symbols,
        "val": plan.val_symbols,
        "test": plan.test_symbols,
    }
    seen: dict[str, str] = {}
    for group_name, symbols in groups.items():
        if not symbols:
            raise RuntimeError(
                f"{plan.family} split {plan.index}: {group_name} symbols가 비어 있습니다."
            )
        for symbol in symbols:
            if symbol not in candles_by_symbol:
                raise RuntimeError(
                    f"{plan.family} split {plan.index}: load되지 않은 symbol입니다: {symbol}"
                )
            if symbol in seen:
                raise RuntimeError(
                    f"{plan.family} split {plan.index}: symbol이 split에 중복 포함되었습니다: "
                    f"{symbol} ({seen[symbol]}, {group_name})"
                )
            seen[symbol] = group_name


# ──────────────────────────────────────────────
# Notebook-extracted training / evaluation logic
# ──────────────────────────────────────────────


def load_vqvae_model(checkpoint_path: Path):
    checkpoint = torch.load(
        Path(checkpoint_path), map_location="cpu", weights_only=True
    )
    model_config = VQVAEConfig(**checkpoint["config"])
    model = VQVAE(model_config)
    model.load_state_dict(checkpoint["state_dict"])
    model.eval()
    return model


def encode_features(model, features: Sequence[PriceShapeFeature]) -> tuple[int, ...]:
    if not features:
        return ()
    inputs = torch.tensor(
        [feature.as_tuple() for feature in features], dtype=torch.float32
    )
    with torch.no_grad():
        z_e = model.encoder(inputs)
        _z_q_st, _z_q, indices = model.quantizer(z_e)
    return tuple(int(index) for index in indices.cpu().tolist())


def reconstruction_mse(model, features: Sequence[PriceShapeFeature]) -> float:
    if not features:
        return 0.0
    inputs = torch.tensor(
        [feature.as_tuple() for feature in features], dtype=torch.float32
    )
    with torch.no_grad():
        reconstruction, *_ = model(inputs)
        loss = torch.mean((reconstruction - inputs) ** 2)
    return float(loss.cpu().item())


def combine_shape_range(
    shape_tokens: Sequence[int], range_buckets: Sequence[int]
) -> tuple[tuple[int, int], ...]:
    return tuple(
        (shape, bucket)
        for shape, bucket in zip(shape_tokens, range_buckets, strict=True)
    )


def counts_for_ids(values: Sequence[int], *, size: int) -> list[int]:
    hist = Counter(values)
    return [hist.get(i, 0) for i in range(size)]


def ratios_for_ids(values: Sequence[int], *, size: int) -> list[float]:
    counts = np.array(counts_for_ids(values, size=size), dtype=float)
    total = counts.sum()
    if total == 0:
        return [0.0 for _ in range(size)]
    return (counts / total).tolist()


def entropy_from_counts(counts: Iterable[int]) -> float:
    total = sum(counts)
    entropy = 0.0
    if total > 0:
        for count in counts:
            if count > 0:
                probability = count / total
                entropy -= probability * log2(probability)
    return float(entropy)


def token_utilization(values: Sequence[int], *, size: int) -> dict[str, object]:
    histogram = dict(sorted(Counter(values).items()))
    utilized_count = sum(1 for i in range(size) if histogram.get(i, 0) > 0)
    return {
        "size": size,
        "utilized_count": utilized_count,
        "dead_count": size - utilized_count,
        "dead_ratio": (size - utilized_count) / size,
        "entropy": entropy_from_counts(counts_for_ids(values, size=size)),
        "histogram": histogram,
    }


def pair_utilization(
    pairs: Sequence[tuple[int, int]], *, shape_size: int, bucket_size: int
) -> dict[str, object]:
    histogram = dict(sorted(Counter(pairs).items()))
    total_size = shape_size * bucket_size
    utilized_count = len(histogram)
    return {
        "size": total_size,
        "utilized_count": utilized_count,
        "dead_count": total_size - utilized_count,
        "dead_ratio": (total_size - utilized_count) / total_size,
        "entropy": entropy_from_counts(histogram.values()),
        "histogram": {
            f"{shape}:{bucket}": count for (shape, bucket), count in histogram.items()
        },
    }


def semantic_consistency(
    tokens: Sequence[int], features: Sequence[PriceShapeFeature]
) -> dict[int, float]:
    groups: dict[int, list[PriceShapeFeature]] = defaultdict(list)
    for token, feature in zip(tokens, features, strict=True):
        groups[token].append(feature)

    result: dict[int, float] = {}
    for token, group in sorted(groups.items()):
        vectors = np.array([feature.as_tuple() for feature in group], dtype=float)
        centroid = vectors.mean(axis=0)
        distances = np.sqrt(((vectors - centroid) ** 2).sum(axis=1))
        result[token] = float(distances.mean())
    return result


def mean_semantic_consistency(
    tokens: Sequence[int], features: Sequence[PriceShapeFeature]
) -> float:
    values = semantic_consistency(tokens, features).values()
    return float(np.mean(list(values))) if values else 0.0


def ratio_diff(
    lhs: Sequence[int], rhs: Sequence[int], *, size: int
) -> dict[str, float]:
    lhs_ratio = np.array(ratios_for_ids(lhs, size=size), dtype=float)
    rhs_ratio = np.array(ratios_for_ids(rhs, size=size), dtype=float)
    diff = np.abs(lhs_ratio - rhs_ratio)
    return {"l1": float(diff.sum()), "max": float(diff.max(initial=0.0))}


def pair_matrix(
    pairs: Sequence[tuple[int, int]], *, shape_size: int, bucket_size: int
) -> np.ndarray:
    matrix = np.zeros((shape_size, bucket_size), dtype=float)
    for shape, bucket in pairs:
        matrix[shape, bucket] += 1
    total = matrix.sum()
    if total > 0:
        matrix /= total
    return matrix


def pair_ratio_diff(
    lhs: Sequence[tuple[int, int]],
    rhs: Sequence[tuple[int, int]],
    *,
    shape_size: int,
    bucket_size: int,
) -> dict[str, float]:
    diff = np.abs(
        pair_matrix(lhs, shape_size=shape_size, bucket_size=bucket_size)
        - pair_matrix(rhs, shape_size=shape_size, bucket_size=bucket_size)
    )
    return {"l1": float(diff.sum()), "max": float(diff.max(initial=0.0))}


def group_by_symbol(
    candles: Sequence[CandleBar],
    shape_tokens: Sequence[int],
    range_buckets: Sequence[int],
) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}
    for candle, shape_token, range_bucket in zip(
        candles, shape_tokens, range_buckets, strict=True
    ):
        entry = rows.setdefault(
            candle.symbol, {"shape_tokens": [], "range_buckets": [], "pairs": []}
        )
        entry["shape_tokens"].append(shape_token)
        entry["range_buckets"].append(range_bucket)
        entry["pairs"].append((shape_token, range_bucket))
    return rows


def rows_for_shape_metrics(
    *,
    model,
    codebook_size: int,
    split_payloads: Sequence[tuple[str, Sequence[int], Sequence[PriceShapeFeature]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split, tokens, features in split_payloads:
        util = token_utilization(tokens, size=codebook_size)
        rows.append(
            {
                "split": split,
                "count": len(tokens),
                "utilized_count": util["utilized_count"],
                "dead_count": util["dead_count"],
                "dead_ratio": round(float(util["dead_ratio"]), 6),
                "entropy": round(float(util["entropy"]), 6),
                "mean_semantic_consistency": round(
                    mean_semantic_consistency(tokens, features), 6
                ),
                "reconstruction_mse": round(reconstruction_mse(model, features), 6),
                "histogram": util["histogram"],
            }
        )
    return rows


def rows_for_token_metrics(
    *, bucket_size: int, split_payloads: Sequence[tuple[str, Sequence[int]]]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split, buckets in split_payloads:
        util = token_utilization(buckets, size=bucket_size)
        rows.append(
            {
                "split": split,
                "count": len(buckets),
                "utilized_count": util["utilized_count"],
                "dead_count": util["dead_count"],
                "dead_ratio": round(float(util["dead_ratio"]), 6),
                "entropy": round(float(util["entropy"]), 6),
                "histogram": util["histogram"],
            }
        )
    return rows


def rows_for_pair_metrics(
    *,
    shape_size: int,
    bucket_size: int,
    split_payloads: Sequence[tuple[str, Sequence[tuple[int, int]]]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for split, pairs in split_payloads:
        util = pair_utilization(pairs, shape_size=shape_size, bucket_size=bucket_size)
        rows.append(
            {
                "split": split,
                "count": len(pairs),
                "utilized_count": util["utilized_count"],
                "dead_count": util["dead_count"],
                "dead_ratio": round(float(util["dead_ratio"]), 6),
                "entropy": round(float(util["entropy"]), 6),
                "histogram": util["histogram"],
            }
        )
    return rows


def per_symbol_rows(
    *,
    candles: Sequence[CandleBar],
    shape_tokens: Sequence[int],
    range_buckets: Sequence[int],
    codebook_size: int,
    bucket_size: int,
) -> list[dict[str, object]]:
    grouped = group_by_symbol(candles, shape_tokens, range_buckets)
    rows: list[dict[str, object]] = []
    for symbol, payload in sorted(grouped.items()):
        symbol_shape_tokens = tuple(payload["shape_tokens"])
        symbol_range_buckets = tuple(payload["range_buckets"])
        symbol_pairs = tuple(payload["pairs"])
        shape_util = token_utilization(symbol_shape_tokens, size=codebook_size)
        range_util = token_utilization(symbol_range_buckets, size=bucket_size)
        pair_util = pair_utilization(
            symbol_pairs, shape_size=codebook_size, bucket_size=bucket_size
        )
        rows.append(
            {
                "symbol": symbol,
                "count": len(symbol_shape_tokens),
                "shape_entropy": round(float(shape_util["entropy"]), 6),
                "range_entropy": round(float(range_util["entropy"]), 6),
                "pair_entropy": round(float(pair_util["entropy"]), 6),
                "shape_histogram": shape_util["histogram"],
                "range_histogram": range_util["histogram"],
                "pair_utilized_count": pair_util["utilized_count"],
            }
        )
    return rows


def run_id_for(plan: SplitPlan, config: RunnerConfig) -> str:
    return (
        f"shape_token_range_bucket_"
        f"{config.market}_{config.interval}_k{config.codebook_size}_"
        f"vge{config.min_volume}_{plan.family}_{plan.index:02d}"
    )


def experiment_config_for(
    *,
    plan: SplitPlan,
    config: RunnerConfig,
    run_dir: Path,
    missing_symbols: Sequence[str],
    skipped_symbols: Sequence[tuple[str, int]],
    volume_filtered_counts: dict[str, int],
    volatility_profile: VolatilityProfile | None,
) -> dict[str, object]:
    exp_config: dict[str, object] = {
        "phase": "1B",
        "experiment": "shape_token_plus_separate_range_bucket",
        "market": config.market,
        "symbols": config.symbol_universe,
        "available_symbols": sorted(
            set(plan.train_symbols + plan.val_symbols + plan.test_symbols)
        ),
        "missing_symbols": list(missing_symbols),
        "skipped_symbols": [
            {"symbol": symbol, "count": count} for symbol, count in skipped_symbols
        ],
        "interval": config.interval,
        "max_candles_per_symbol": config.max_candles_per_symbol,
        "min_candles_per_symbol": config.min_candles_per_symbol,
        "min_volume": config.min_volume,
        "volume_filter": f"volume >= {config.min_volume}",
        "volume_filtered_counts": {
            symbol: count
            for symbol, count in sorted(volume_filtered_counts.items())
            if count > 0
        },
        "codebook_size": config.codebook_size,
        "latent_dim": config.latent_dim,
        "hidden_dim": config.hidden_dim,
        "epochs": config.epochs,
        "batch_size": config.batch_size,
        "learning_rate": config.learning_rate,
        "seed": plan.seed,
        "kmeans_n_init": config.kmeans_n_init,
        "kmeans_max_iter": config.kmeans_max_iter,
        "range_bucket_quantiles": config.range_bucket_quantiles,
        "range_bucket_labels": config.range_bucket_labels,
        "warehouse_path": str(config.warehouse_path),
        "run_dir": str(run_dir),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "split_family": plan.family,
        "split_index": plan.index,
        "split_seed": plan.seed,
        "train_symbols": plan.train_symbols,
        "val_symbols": plan.val_symbols,
        "test_symbols": plan.test_symbols,
    }
    if volatility_profile is not None:
        exp_config["volatility_profile"] = {
            "metric": "median_log_range_pct",
            "low_medium_boundary": volatility_profile.boundaries[0],
            "medium_high_boundary": volatility_profile.boundaries[1],
            "symbol_values": volatility_profile.values,
            "groups": volatility_profile.groups,
        }
    return exp_config


def run_experiment(
    *,
    plan: SplitPlan,
    config: RunnerConfig,
    candles_by_symbol: dict[str, tuple[CandleBar, ...]],
    missing_symbols: Sequence[str],
    skipped_symbols: Sequence[tuple[str, int]],
    volume_filtered_counts: dict[str, int],
    volatility_profile: VolatilityProfile | None,
) -> dict[str, object]:
    validate_plan_symbols(plan, candles_by_symbol)
    run_id = run_id_for(plan, config)
    run_dir = config.runs_dir / run_id
    figures_dir = run_dir / "figures"
    if run_dir.exists():
        raise FileExistsError(
            f"run directory already exists; refusing to overwrite: {run_dir}"
        )

    run_dir.mkdir(parents=True)
    figures_dir.mkdir(parents=True)
    set_reproducible_seed(plan.seed)

    exp_config = experiment_config_for(
        plan=plan,
        config=config,
        run_dir=run_dir,
        missing_symbols=missing_symbols,
        skipped_symbols=skipped_symbols,
        volume_filtered_counts=volume_filtered_counts,
        volatility_profile=volatility_profile,
    )
    (run_dir / "experiment_config.json").write_text(
        json.dumps(exp_config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    train_candles = tuple(
        candle for symbol in plan.train_symbols for candle in candles_by_symbol[symbol]
    )
    val_candles = tuple(
        candle for symbol in plan.val_symbols for candle in candles_by_symbol[symbol]
    )
    test_candles = tuple(
        candle for symbol in plan.test_symbols for candle in candles_by_symbol[symbol]
    )
    if not train_candles or not val_candles or not test_candles:
        raise RuntimeError("train/val/test split must not be empty")

    train_features = extract_price_shape_features(train_candles)
    val_features = extract_price_shape_features(val_candles)
    test_features = extract_price_shape_features(test_candles)

    # No leakage: fit range bucketizer on train candles only.
    range_bucketizer = fit_range_bucketizer(
        train_candles,
        quantiles=config.range_bucket_quantiles,
        labels=config.range_bucket_labels,
    )
    train_range_buckets = encode_range_buckets(train_candles, range_bucketizer)
    val_range_buckets = encode_range_buckets(val_candles, range_bucketizer)
    test_range_buckets = encode_range_buckets(test_candles, range_bucketizer)

    train_config = TrainConfig(
        output_dir=run_dir,
        model=VQVAEConfig(
            input_dim=len(FEATURE_NAMES),
            codebook_size=config.codebook_size,
            latent_dim=config.latent_dim,
            hidden_dim=config.hidden_dim,
        ),
        epochs=config.epochs,
        batch_size=config.batch_size,
        learning_rate=config.learning_rate,
        seed=plan.seed,
    )
    train_result = train(train_features, config=train_config)
    model = load_vqvae_model(train_result.checkpoint_path)

    train_shape_tokens = encode_features(model, train_features)
    val_shape_tokens = encode_features(model, val_features)
    test_shape_tokens = encode_features(model, test_features)
    train_pairs = combine_shape_range(train_shape_tokens, train_range_buckets)
    val_pairs = combine_shape_range(val_shape_tokens, val_range_buckets)
    test_pairs = combine_shape_range(test_shape_tokens, test_range_buckets)

    bucket_size = len(config.range_bucket_labels)
    shape_rows = rows_for_shape_metrics(
        model=model,
        codebook_size=config.codebook_size,
        split_payloads=(
            ("train", train_shape_tokens, train_features),
            ("val", val_shape_tokens, val_features),
            ("test", test_shape_tokens, test_features),
        ),
    )
    range_rows = rows_for_token_metrics(
        bucket_size=bucket_size,
        split_payloads=(
            ("train", train_range_buckets),
            ("val", val_range_buckets),
            ("test", test_range_buckets),
        ),
    )
    pair_rows = rows_for_pair_metrics(
        shape_size=config.codebook_size,
        bucket_size=bucket_size,
        split_payloads=(
            ("train", train_pairs),
            ("val", val_pairs),
            ("test", test_pairs),
        ),
    )

    x_train = feature_matrix(train_features)
    x_val = feature_matrix(val_features)
    x_test = feature_matrix(test_features)
    kmeans_model = KMeans(
        n_clusters=config.codebook_size,
        random_state=plan.seed,
        n_init=config.kmeans_n_init,
        max_iter=config.kmeans_max_iter,
    )
    kmeans_train_shape_tokens = tuple(
        int(x) for x in kmeans_model.fit_predict(x_train).tolist()
    )
    kmeans_val_shape_tokens = tuple(
        int(x) for x in kmeans_model.predict(x_val).tolist()
    )
    kmeans_test_shape_tokens = tuple(
        int(x) for x in kmeans_model.predict(x_test).tolist()
    )
    kmeans_train_pairs = combine_shape_range(
        kmeans_train_shape_tokens, train_range_buckets
    )
    kmeans_val_pairs = combine_shape_range(kmeans_val_shape_tokens, val_range_buckets)
    kmeans_test_pairs = combine_shape_range(
        kmeans_test_shape_tokens, test_range_buckets
    )
    kmeans_train_mean_sc = mean_semantic_consistency(
        kmeans_train_shape_tokens, train_features
    )
    kmeans_val_mean_sc = mean_semantic_consistency(
        kmeans_val_shape_tokens, val_features
    )
    kmeans_test_mean_sc = mean_semantic_consistency(
        kmeans_test_shape_tokens, test_features
    )

    all_candles = train_candles + val_candles + test_candles
    all_shape_tokens = train_shape_tokens + val_shape_tokens + test_shape_tokens
    all_range_buckets = train_range_buckets + val_range_buckets + test_range_buckets
    symbol_rows = per_symbol_rows(
        candles=all_candles,
        shape_tokens=all_shape_tokens,
        range_buckets=all_range_buckets,
        codebook_size=config.codebook_size,
        bucket_size=bucket_size,
    )

    metrics = {
        "config": exp_config,
        "feature": {
            "shape_feature_names": FEATURE_NAMES,
            "range_bucketizer": {
                "quantiles": range_bucketizer.quantiles,
                "edges": range_bucketizer.edges,
                "labels": range_bucketizer.labels,
            },
        },
        "split": {
            "train_symbols": plan.train_symbols,
            "val_symbols": plan.val_symbols,
            "test_symbols": plan.test_symbols,
            "train_candles": len(train_candles),
            "val_candles": len(val_candles),
            "test_candles": len(test_candles),
        },
        "vqvae_shape": {
            "train_result": {
                "checkpoint_path": str(train_result.checkpoint_path),
                "epochs": train_result.epochs,
                "final_loss": train_result.final_loss,
            },
            "rows": shape_rows,
            "val_train_ratio_diff": ratio_diff(
                val_shape_tokens, train_shape_tokens, size=config.codebook_size
            ),
            "test_train_ratio_diff": ratio_diff(
                test_shape_tokens, train_shape_tokens, size=config.codebook_size
            ),
        },
        "range_bucket": {
            "rows": range_rows,
            "val_train_ratio_diff": ratio_diff(
                val_range_buckets, train_range_buckets, size=bucket_size
            ),
            "test_train_ratio_diff": ratio_diff(
                test_range_buckets, train_range_buckets, size=bucket_size
            ),
        },
        "shape_range_pair": {
            "rows": pair_rows,
            "val_train_ratio_diff": pair_ratio_diff(
                val_pairs,
                train_pairs,
                shape_size=config.codebook_size,
                bucket_size=bucket_size,
            ),
            "test_train_ratio_diff": pair_ratio_diff(
                test_pairs,
                train_pairs,
                shape_size=config.codebook_size,
                bucket_size=bucket_size,
            ),
        },
        "kmeans_shape": {
            "params": kmeans_model.get_params(),
            "inertia_total": float(kmeans_model.inertia_),
            "inertia_per_sample": float(kmeans_model.inertia_ / len(x_train)),
            "shape_val_train_ratio_diff": ratio_diff(
                kmeans_val_shape_tokens,
                kmeans_train_shape_tokens,
                size=config.codebook_size,
            ),
            "shape_test_train_ratio_diff": ratio_diff(
                kmeans_test_shape_tokens,
                kmeans_train_shape_tokens,
                size=config.codebook_size,
            ),
            "pair_val_train_ratio_diff": pair_ratio_diff(
                kmeans_val_pairs,
                kmeans_train_pairs,
                shape_size=config.codebook_size,
                bucket_size=bucket_size,
            ),
            "pair_test_train_ratio_diff": pair_ratio_diff(
                kmeans_test_pairs,
                kmeans_train_pairs,
                shape_size=config.codebook_size,
                bucket_size=bucket_size,
            ),
            "mean_semantic_consistency_train": kmeans_train_mean_sc,
            "mean_semantic_consistency_val": kmeans_val_mean_sc,
            "mean_semantic_consistency_test": kmeans_test_mean_sc,
        },
        "per_symbol": symbol_rows,
    }
    (run_dir / "metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    save_figures(
        figures_dir=figures_dir,
        codebook_size=config.codebook_size,
        bucket_size=bucket_size,
        range_labels=config.range_bucket_labels,
        train_shape_tokens=train_shape_tokens,
        val_shape_tokens=val_shape_tokens,
        test_shape_tokens=test_shape_tokens,
        train_range_buckets=train_range_buckets,
        val_range_buckets=val_range_buckets,
        test_range_buckets=test_range_buckets,
        train_pairs=train_pairs,
        val_pairs=val_pairs,
        test_pairs=test_pairs,
        per_symbol=group_by_symbol(all_candles, all_shape_tokens, all_range_buckets),
        kmeans_train_shape_tokens=kmeans_train_shape_tokens,
    )

    train_shape_row = next(row for row in shape_rows if row["split"] == "train")
    if float(train_shape_row["dead_ratio"]) > 0.5:
        warnings.warn(
            f"{run_id}: VQ-VAE dead token ratio가 0.5를 초과했습니다 "
            f"({train_shape_row['dead_count']} / {config.codebook_size}). artifacts는 저장했습니다.",
            stacklevel=2,
        )

    print_run_summary(
        run_id=run_id, metrics=metrics, codebook_size=config.codebook_size
    )
    return metrics


# ──────────────────────────────────────────────
# Figures
# ──────────────────────────────────────────────


def save_current_figure(figures_dir: Path, filename: str) -> Path:
    path = figures_dir / filename
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    return path


def save_figures(
    *,
    figures_dir: Path,
    codebook_size: int,
    bucket_size: int,
    range_labels: Sequence[str],
    train_shape_tokens: Sequence[int],
    val_shape_tokens: Sequence[int],
    test_shape_tokens: Sequence[int],
    train_range_buckets: Sequence[int],
    val_range_buckets: Sequence[int],
    test_range_buckets: Sequence[int],
    train_pairs: Sequence[tuple[int, int]],
    val_pairs: Sequence[tuple[int, int]],
    test_pairs: Sequence[tuple[int, int]],
    per_symbol: dict[str, dict[str, object]],
    kmeans_train_shape_tokens: Sequence[int],
) -> None:
    width = 0.25

    x = np.arange(codebook_size)
    plt.figure(figsize=(13, 4))
    plt.bar(
        x - width,
        ratios_for_ids(train_shape_tokens, size=codebook_size),
        width=width,
        label="train",
    )
    plt.bar(
        x,
        ratios_for_ids(val_shape_tokens, size=codebook_size),
        width=width,
        label="val",
    )
    plt.bar(
        x + width,
        ratios_for_ids(test_shape_tokens, size=codebook_size),
        width=width,
        label="test",
    )
    plt.title("VQ-VAE Shape Token Ratio — Train / Val / Test")
    plt.xlabel("Shape Token ID")
    plt.ylabel("Ratio")
    plt.xticks(range(codebook_size))
    plt.legend()
    plt.tight_layout()
    save_current_figure(figures_dir, "01_shape_token_ratio_histogram.png")

    x = np.arange(bucket_size)
    plt.figure(figsize=(10, 4))
    plt.bar(
        x - width,
        ratios_for_ids(train_range_buckets, size=bucket_size),
        width=width,
        label="train",
    )
    plt.bar(
        x, ratios_for_ids(val_range_buckets, size=bucket_size), width=width, label="val"
    )
    plt.bar(
        x + width,
        ratios_for_ids(test_range_buckets, size=bucket_size),
        width=width,
        label="test",
    )
    plt.title("Separate Range Bucket Ratio — Train / Val / Test")
    plt.xlabel("Range Bucket")
    plt.ylabel("Ratio")
    plt.xticks(range(bucket_size), range_labels, rotation=30, ha="right")
    plt.legend()
    plt.tight_layout()
    save_current_figure(figures_dir, "02_range_bucket_ratio_histogram.png")

    fig, axes = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    im = None
    for ax, title, pairs in [
        (axes[0], "train", train_pairs),
        (axes[1], "val", val_pairs),
        (axes[2], "test", test_pairs),
    ]:
        matrix = pair_matrix(pairs, shape_size=codebook_size, bucket_size=bucket_size)
        im = ax.imshow(matrix, aspect="auto", cmap="viridis")
        ax.set_title(title)
        ax.set_xlabel("Range Bucket")
        ax.set_xticks(range(bucket_size), range_labels, rotation=45, ha="right")
        ax.set_yticks(range(codebook_size), range(codebook_size))
    axes[0].set_ylabel("Shape Token ID")
    if im is not None:
        fig.colorbar(im, ax=axes, label="Split-level pair ratio")
    fig.suptitle("Shape Token × Range Bucket Distribution", y=1.02)
    plt.tight_layout()
    save_current_figure(figures_dir, "03_shape_range_pair_heatmap.png")

    symbols_for_plot = sorted(per_symbol)
    range_heatmap = np.zeros((len(symbols_for_plot), bucket_size), dtype=float)
    for row_index, symbol in enumerate(symbols_for_plot):
        buckets = tuple(per_symbol[symbol]["range_buckets"])
        counts = np.array(counts_for_ids(buckets, size=bucket_size), dtype=float)
        total = counts.sum()
        if total > 0:
            range_heatmap[row_index, :] = counts / total
    plt.figure(figsize=(10, max(4, len(symbols_for_plot) * 0.45)))
    plt.imshow(range_heatmap, aspect="auto", cmap="magma")
    plt.colorbar(label="Within-symbol range bucket ratio")
    plt.yticks(range(len(symbols_for_plot)), symbols_for_plot)
    plt.xticks(range(bucket_size), range_labels, rotation=30, ha="right")
    plt.title("Per-symbol Range Bucket Distribution")
    plt.xlabel("Range Bucket")
    plt.ylabel("Symbol")
    plt.tight_layout()
    save_current_figure(figures_dir, "04_per_symbol_range_bucket_heatmap.png")

    shape_heatmap = np.zeros((len(symbols_for_plot), codebook_size), dtype=float)
    for row_index, symbol in enumerate(symbols_for_plot):
        tokens = tuple(per_symbol[symbol]["shape_tokens"])
        counts = np.array(counts_for_ids(tokens, size=codebook_size), dtype=float)
        total = counts.sum()
        if total > 0:
            shape_heatmap[row_index, :] = counts / total
    plt.figure(figsize=(12, max(4, len(symbols_for_plot) * 0.45)))
    plt.imshow(shape_heatmap, aspect="auto", cmap="viridis")
    plt.colorbar(label="Within-symbol shape token ratio")
    plt.yticks(range(len(symbols_for_plot)), symbols_for_plot)
    plt.xticks(range(codebook_size), range(codebook_size))
    plt.title("Per-symbol Shape Token Distribution")
    plt.xlabel("Shape Token ID")
    plt.ylabel("Symbol")
    plt.tight_layout()
    save_current_figure(figures_dir, "05_per_symbol_shape_token_heatmap.png")

    x = np.arange(codebook_size)
    plt.figure(figsize=(13, 4))
    plt.bar(
        x - 0.2,
        counts_for_ids(train_shape_tokens, size=codebook_size),
        width=0.4,
        label="VQ-VAE shape train",
    )
    plt.bar(
        x + 0.2,
        counts_for_ids(kmeans_train_shape_tokens, size=codebook_size),
        width=0.4,
        label="KMeans shape train",
    )
    plt.title("VQ-VAE vs KMeans Shape Token/Cluster Distribution")
    plt.xlabel("Shape Token / Cluster ID")
    plt.ylabel("Count")
    plt.xticks(range(codebook_size))
    plt.legend()
    plt.tight_layout()
    save_current_figure(figures_dir, "06_vqvae_vs_kmeans_shape_histogram.png")


def row_by_split(rows: Sequence[dict[str, object]], split: str) -> dict[str, object]:
    for row in rows:
        if row.get("split") == split:
            return row
    return {}


def print_run_summary(
    *, run_id: str, metrics: dict[str, object], codebook_size: int
) -> None:
    split = metrics["split"]
    vqvae = metrics["vqvae_shape"]
    range_bucket = metrics["range_bucket"]
    pair = metrics["shape_range_pair"]
    train_shape = row_by_split(vqvae["rows"], "train")
    print(f"[{run_id}]")
    print("train symbols :", " ".join(split["train_symbols"]))
    print("val symbols   :", " ".join(split["val_symbols"]))
    print("test symbols  :", " ".join(split["test_symbols"]))
    print(
        "candles       : "
        f"train={split['train_candles']}  val={split['val_candles']}  test={split['test_candles']}"
    )
    print(f"shape_test_l1 : {vqvae['test_train_ratio_diff']['l1']:.4f}")
    print(f"range_test_l1 : {range_bucket['test_train_ratio_diff']['l1']:.4f}")
    print(f"pair_test_l1  : {pair['test_train_ratio_diff']['l1']:.4f}")
    print(f"dead tokens   : {train_shape.get('dead_count')} / {codebook_size}")


# ──────────────────────────────────────────────
# CLI / orchestration
# ──────────────────────────────────────────────


def print_dry_run(
    *,
    config: RunnerConfig,
    candles_by_symbol: dict[str, tuple[CandleBar, ...]],
    volume_filtered_counts: dict[str, int],
    volatility_profile: VolatilityProfile | None,
    plans: Sequence[SplitPlan],
) -> None:
    print("DRY RUN — training을 실행하지 않고 run directory도 생성하지 않습니다.")
    print(f"Volume filter: volume >= {config.min_volume}")
    print("Symbol universe after volume/min-candle filtering:")
    for symbol in sorted(candles_by_symbol):
        print(
            f"  {symbol:6s} candles={len(candles_by_symbol[symbol])} "
            f"volume_filtered={volume_filtered_counts.get(symbol, 0)}"
        )

    if volatility_profile is not None:
        print("Volatility tertile boundaries:")
        print(f"  low/medium : {volatility_profile.boundaries[0]:.10f}")
        print(f"  medium/high: {volatility_profile.boundaries[1]:.10f}")
        print("Volatility groups:")
        for group_name in ("low", "medium", "high"):
            symbols = volatility_profile.groups[group_name]
            print(f"  {group_name:6s}: {' '.join(symbols)}")

    print("Planned splits:")
    for plan in plans:
        print(f"[{run_id_for(plan, config)}] seed={plan.seed}")
        print("  train:", " ".join(plan.train_symbols))
        print("  val  :", " ".join(plan.val_symbols))
        print("  test :", " ".join(plan.test_symbols))


def collect_metrics(runs_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "collect_metrics.py"),
            "--runs-dir",
            str(runs_dir),
            "--out",
            str(PHASE_DIR / "summaries" / "summary.csv"),
        ],
        check=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--split-family",
        choices=["random", "vol_strat", "vol_holdout", "stress"],
        required=True,
    )
    parser.add_argument("--n-runs", type=int, default=1)
    parser.add_argument("--seed-start", type=int, default=0)
    parser.add_argument("--market", default="NASDAQ")
    parser.add_argument("--interval", default="1m")
    parser.add_argument("--codebook-size", type=int, default=12)
    parser.add_argument("--max-candles-per-symbol", type=int, default=12_000)
    parser.add_argument("--min-candles-per-symbol", type=int, default=500)
    parser.add_argument(
        "--min-volume",
        type=int,
        default=2,
        help="Keep candles with volume >= this value. Default 2 excludes volume <= 1.",
    )
    parser.add_argument("--train-symbol-ratio", type=float, default=0.70)
    parser.add_argument("--val-symbol-ratio", type=float, default=0.15)
    parser.add_argument("--symbol-universe", nargs="+", default=DEFAULT_SYMBOL_UNIVERSE)
    parser.add_argument("--train-symbols", nargs="+")
    parser.add_argument("--val-symbols", nargs="+")
    parser.add_argument("--test-symbols", nargs="+")
    parser.add_argument(
        "--runs-dir", type=Path, default=PHASE_DIR / "runs" / "phase_1b"
    )
    parser.add_argument("--warehouse-path", type=Path, default=default_warehouse_file())
    parser.add_argument("--latent-dim", type=int, default=16)
    parser.add_argument("--hidden-dim", type=int, default=64)
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--kmeans-n-init", type=int, default=20)
    parser.add_argument("--kmeans-max-iter", type=int, default=300)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def validate_args(args: argparse.Namespace) -> None:
    if args.n_runs <= 0:
        raise ValueError("--n-runs must be positive")
    if not 0 < args.train_symbol_ratio < 1:
        raise ValueError("--train-symbol-ratio must be between 0 and 1")
    if not 0 <= args.val_symbol_ratio < 1:
        raise ValueError("--val-symbol-ratio must be between 0 and 1")
    if args.train_symbol_ratio + args.val_symbol_ratio >= 1:
        raise ValueError(
            "--train-symbol-ratio + --val-symbol-ratio must be less than 1"
        )
    if args.codebook_size <= 1:
        raise ValueError("--codebook-size must be greater than 1")
    if args.max_candles_per_symbol <= 0 or args.min_candles_per_symbol <= 0:
        raise ValueError("candle count limits must be positive")
    if args.min_volume < 0:
        raise ValueError("--min-volume must be non-negative")


def main() -> None:
    args = parse_args()
    validate_args(args)

    config = RunnerConfig(
        market=args.market,
        interval=args.interval,
        codebook_size=args.codebook_size,
        max_candles_per_symbol=args.max_candles_per_symbol,
        min_candles_per_symbol=args.min_candles_per_symbol,
        min_volume=args.min_volume,
        train_symbol_ratio=args.train_symbol_ratio,
        val_symbol_ratio=args.val_symbol_ratio,
        symbol_universe=list(args.symbol_universe),
        runs_dir=args.runs_dir,
        warehouse_path=args.warehouse_path,
        latent_dim=args.latent_dim,
        hidden_dim=args.hidden_dim,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        kmeans_n_init=args.kmeans_n_init,
        kmeans_max_iter=args.kmeans_max_iter,
        range_bucket_quantiles=DEFAULT_RANGE_BUCKET_QUANTILES,
        range_bucket_labels=DEFAULT_RANGE_BUCKET_LABELS,
    )

    (
        candles_by_symbol,
        missing_symbols,
        skipped_symbols,
        volume_filtered_counts,
    ) = load_symbol_candles(config)
    volatility_profile = (
        compute_volatility_profile(candles_by_symbol)
        if args.split_family in {"vol_strat", "vol_holdout"}
        else None
    )
    plans = make_split_plans(
        family=args.split_family,
        n_runs=args.n_runs,
        seed_start=args.seed_start,
        config=config,
        available_symbols=list(candles_by_symbol),
        volatility_profile=volatility_profile,
        stress_train_symbols=args.train_symbols,
        stress_val_symbols=args.val_symbols,
        stress_test_symbols=args.test_symbols,
    )
    for plan in plans:
        validate_plan_symbols(plan, candles_by_symbol)

    if args.dry_run:
        print_dry_run(
            config=config,
            candles_by_symbol=candles_by_symbol,
            volume_filtered_counts=volume_filtered_counts,
            volatility_profile=volatility_profile,
            plans=plans,
        )
        return

    existing_dirs = [
        config.runs_dir / run_id_for(plan, config)
        for plan in plans
        if (config.runs_dir / run_id_for(plan, config)).exists()
    ]
    if existing_dirs:
        formatted = "\n".join(f"  {path}" for path in existing_dirs)
        raise FileExistsError(
            f"target run directory already exists; refusing to overwrite:\n{formatted}"
        )

    for plan in plans:
        run_experiment(
            plan=plan,
            config=config,
            candles_by_symbol=candles_by_symbol,
            missing_symbols=missing_symbols,
            skipped_symbols=skipped_symbols,
            volume_filtered_counts=volume_filtered_counts,
            volatility_profile=volatility_profile,
        )

    collect_metrics(config.runs_dir)


if __name__ == "__main__":
    main()
