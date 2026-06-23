"""Pure-Python ranking, regression, and binary metrics for surge evaluation.

The objective is ranking, so the headline numbers are rank-based: per-day NDCG@k,
Precision@k, and mean average precision over the day's candidates, plus Spearman
rank correlation against the continuous target. ROC-AUC and PR-AUC summarize the
binary surge view (PR-AUC matters because surges are rare).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from modules.news.intelligence.modeling.dataset import SurgeSample


@dataclass(frozen=True, slots=True)
class RankingReport:
    n: int
    n_days: int
    n_positive: int
    k: int
    spearman: float
    ndcg_at_k: float
    precision_at_k: float
    mean_average_precision: float
    roc_auc: float | None
    pr_auc: float | None


def evaluate_ranking(
    samples: Sequence[SurgeSample],
    scores: Sequence[float],
    *,
    k: int = 10,
) -> RankingReport:
    if len(samples) != len(scores):
        raise ValueError("samples and scores must align")
    if k <= 0:
        raise ValueError("k must be positive")

    regression_pairs = [
        (score, sample.abnormal_return_std)
        for sample, score in zip(samples, scores)
        if sample.abnormal_return_std is not None
    ]
    spearman_value = (
        spearman([p for p, _ in regression_pairs], [t for _, t in regression_pairs])
        if len(regression_pairs) >= 2
        else 0.0
    )

    by_day: dict[str, list[tuple[float, SurgeSample]]] = {}
    for sample, score in zip(samples, scores):
        by_day.setdefault(sample.anchor.date().isoformat(), []).append((score, sample))

    ndcg_values: list[float] = []
    precision_values: list[float] = []
    average_precisions: list[float] = []
    for ranked in by_day.values():
        ranked.sort(key=lambda item: (-item[0], item[1].sample_id))
        relevances = [float(sample.surge_label) for _, sample in ranked]
        ndcg_values.append(ndcg_at_k(relevances, k))
        precision_values.append(precision_at_k(relevances, k))
        average_precisions.append(average_precision(relevances))

    labels = [sample.surge_label for sample in samples]
    return RankingReport(
        n=len(samples),
        n_days=len(by_day),
        n_positive=sum(labels),
        k=k,
        spearman=spearman_value,
        ndcg_at_k=_mean(ndcg_values),
        precision_at_k=_mean(precision_values),
        mean_average_precision=_mean(average_precisions),
        roc_auc=roc_auc(list(scores), labels),
        pr_auc=pr_auc(list(scores), labels),
    )


def spearman(predicted: Sequence[float], actual: Sequence[float]) -> float:
    if len(predicted) != len(actual) or len(predicted) < 2:
        return 0.0
    return _pearson(_ranks(predicted), _ranks(actual))


def ndcg_at_k(relevances: Sequence[float], k: int) -> float:
    dcg = _dcg(relevances[:k])
    ideal = _dcg(sorted(relevances, reverse=True)[:k])
    return dcg / ideal if ideal > 0 else 0.0


def precision_at_k(relevances: Sequence[float], k: int) -> float:
    if not relevances:
        return 0.0
    top = relevances[: min(k, len(relevances))]
    return sum(1 for value in top if value > 0) / len(top)


def average_precision(relevances: Sequence[float]) -> float:
    positives = sum(1 for value in relevances if value > 0)
    if positives == 0:
        return 0.0
    hits = 0
    score = 0.0
    for index, value in enumerate(relevances, start=1):
        if value > 0:
            hits += 1
            score += hits / index
    return score / positives


def roc_auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    positives = sum(1 for label in labels if label == 1)
    negatives = len(labels) - positives
    if positives == 0 or negatives == 0:
        return None
    ranks = _ranks(scores)
    rank_sum = sum(rank for rank, label in zip(ranks, labels) if label == 1)
    return (rank_sum - positives * (positives + 1) / 2) / (positives * negatives)


def pr_auc(scores: Sequence[float], labels: Sequence[int]) -> float | None:
    positives = sum(1 for label in labels if label == 1)
    if positives == 0 or positives == len(labels):
        return None
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], i))
    ordered_labels = [float(labels[i]) for i in order]
    return average_precision(ordered_labels)


def _dcg(relevances: Sequence[float]) -> float:
    return sum(
        relevance / math.log2(index + 2)
        for index, relevance in enumerate(relevances)
    )


def _ranks(values: Sequence[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        end = index
        while end + 1 < len(order) and values[order[end + 1]] == values[order[index]]:
            end += 1
        average_rank = (index + end) / 2 + 1  # 1-based average rank for ties
        for position in range(index, end + 1):
            ranks[order[position]] = average_rank
        index = end + 1
    return ranks


def _pearson(left: Sequence[float], right: Sequence[float]) -> float:
    n = len(left)
    mean_left = sum(left) / n
    mean_right = sum(right) / n
    covariance = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left, right)
    )
    var_left = sum((a - mean_left) ** 2 for a in left)
    var_right = sum((b - mean_right) ** 2 for b in right)
    if var_left == 0 or var_right == 0:
        return 0.0
    return covariance / math.sqrt(var_left * var_right)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0
