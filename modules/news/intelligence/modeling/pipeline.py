"""Train a surge-score regressor and evaluate it the way it will be used live.

The model is fit on the in-time training fold and scored on the IID (event-hash)
validation/test folds and the forward-in-time out-of-time holdout. The headline is
the out-of-time ranking quality; baselines (turnover z-score, constant) and slices
(by sample origin and anchor adjustment) sit alongside it so the label-design work
can be judged, not just the model.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from modules.news.intelligence.modeling.dataset import (
    DataSplits,
    SurgeSample,
    partition,
)
from modules.news.intelligence.modeling.features import (
    TextEmbedder,
    build_features,
)
from modules.news.intelligence.modeling.metrics import RankingReport, evaluate_ranking
from modules.news.intelligence.modeling.model import RidgeRegressor, SurgeModel


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    n_train: int
    k: int
    validation: RankingReport
    iid_test: RankingReport
    out_of_time_test: RankingReport
    baselines: dict[str, RankingReport]
    slices: dict[str, RankingReport]

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_train": self.n_train,
            "k": self.k,
            "validation": _report_dict(self.validation),
            "iid_test": _report_dict(self.iid_test),
            "out_of_time_test": _report_dict(self.out_of_time_test),
            "baselines": {
                name: _report_dict(report) for name, report in self.baselines.items()
            },
            "slices": {
                name: _report_dict(report) for name, report in self.slices.items()
            },
        }


def train_and_evaluate(
    rows: Sequence[SurgeSample],
    *,
    embedder: TextEmbedder,
    model_factory: Callable[[], SurgeModel] = RidgeRegressor,
    k: int = 10,
    out_of_time_fraction: float = 0.2,
) -> EvaluationReport:
    splits = partition(rows, out_of_time_fraction=out_of_time_fraction)
    train_rows = [row for row in splits.train if row.has_regression_target]
    if not train_rows:
        raise ValueError("no training rows carry a regression target")

    matrix = build_features(train_rows, embedder)
    model = model_factory()
    model.fit(matrix.rows, [float(value) for value in matrix.regression_target])

    def score(subset: Sequence[SurgeSample]) -> list[float]:
        if not subset:
            return []
        return model.predict(build_features(subset, embedder).rows)

    oot_scores = score(splits.out_of_time_test)
    return EvaluationReport(
        n_train=len(train_rows),
        k=k,
        validation=evaluate_ranking(splits.validation, score(splits.validation), k=k),
        iid_test=evaluate_ranking(splits.iid_test, score(splits.iid_test), k=k),
        out_of_time_test=evaluate_ranking(splits.out_of_time_test, oot_scores, k=k),
        baselines=_baselines(splits, k=k),
        slices=_slices(splits.out_of_time_test, oot_scores, k=k),
    )


def _baselines(splits: DataSplits, *, k: int) -> dict[str, RankingReport]:
    rows = splits.out_of_time_test
    turnover_scores = [row.turnover_zscore or 0.0 for row in rows]
    constant_scores = [0.0 for _ in rows]
    return {
        "turnover_zscore": evaluate_ranking(rows, turnover_scores, k=k),
        "constant": evaluate_ranking(rows, constant_scores, k=k),
    }


def _slices(
    rows: Sequence[SurgeSample], scores: Sequence[float], *, k: int
) -> dict[str, RankingReport]:
    slices: dict[str, RankingReport] = {}
    for dimension, value in (
        ("origin", "event_selected"),
        ("origin", "random_control"),
        ("anchor", "none"),
        ("anchor", "rolled_to_next_session"),
    ):
        selected = [
            (sample, scored)
            for sample, scored in zip(rows, scores)
            if (sample.sample_origin if dimension == "origin" else sample.anchor_adjustment)
            == value
        ]
        if not selected:
            continue
        slices[f"{dimension}:{value}"] = evaluate_ranking(
            [sample for sample, _ in selected],
            [scored for _, scored in selected],
            k=k,
        )
    return slices


def _report_dict(report: RankingReport) -> dict[str, Any]:
    return {
        "n": report.n,
        "n_days": report.n_days,
        "n_positive": report.n_positive,
        "k": report.k,
        "spearman": report.spearman,
        "ndcg_at_k": report.ndcg_at_k,
        "precision_at_k": report.precision_at_k,
        "mean_average_precision": report.mean_average_precision,
        "roc_auc": report.roc_auc,
        "pr_auc": report.pr_auc,
    }
