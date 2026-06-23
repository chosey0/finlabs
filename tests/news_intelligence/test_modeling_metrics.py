from __future__ import annotations

import math
from datetime import datetime, timedelta

from modules.domain.news_intelligence import KST
from modules.news.intelligence.modeling.dataset import SurgeSample
from modules.news.intelligence.modeling.metrics import (
    average_precision,
    evaluate_ranking,
    ndcg_at_k,
    precision_at_k,
    pr_auc,
    roc_auc,
    spearman,
)


def test_precision_and_average_precision_are_rank_aware() -> None:
    assert precision_at_k([1, 0, 1, 0], 2) == 0.5
    # AP for relevances [0, 1, 1]: (1/2 + 2/3) / 2
    assert average_precision([0, 1, 1]) == (0.5 + 2 / 3) / 2


def test_ndcg_rewards_putting_relevant_items_first() -> None:
    good = ndcg_at_k([1, 0, 0], 3)
    bad = ndcg_at_k([0, 0, 1], 3)
    assert good == 1.0
    assert bad < good


def test_spearman_is_one_for_monotone_and_minus_one_for_reversed() -> None:
    assert spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert spearman([1, 2, 3, 4], [40, 30, 20, 10]) == -1.0


def test_roc_and_pr_auc_match_known_values() -> None:
    scores = [0.1, 0.4, 0.35, 0.8]
    labels = [0, 0, 1, 1]
    assert roc_auc(scores, labels) == 0.75
    assert pr_auc(scores, labels) is not None
    # Single-class inputs are undefined and return None.
    assert roc_auc([0.1, 0.2], [1, 1]) is None


def test_evaluate_ranking_groups_by_day_and_summarizes() -> None:
    day = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    samples = (
        _sample("a", day, std=3.0, surge=1),
        _sample("b", day + timedelta(minutes=1), std=0.1, surge=0),
        _sample("c", day + timedelta(days=1), std=2.5, surge=1),
        _sample("d", day + timedelta(days=1, minutes=1), std=0.2, surge=0),
    )
    # Scores that rank the surging name first on each day.
    scores = [0.9, 0.1, 0.8, 0.2]

    report = evaluate_ranking(samples, scores, k=2)

    assert report.n == 4
    assert report.n_days == 2
    assert report.n_positive == 2
    assert report.precision_at_k == 0.5  # one of two top-2 per day is a surge
    assert math.isclose(report.ndcg_at_k, 1.0)
    assert report.spearman > 0.9  # scores track the continuous target


def _sample(sample_id: str, anchor: datetime, *, std: float, surge: int) -> SurgeSample:
    return SurgeSample(
        sample_id=sample_id,
        security_id=f"KOSDAQ:{sample_id}",
        market="KOSDAQ",
        anchor=anchor,
        event_id=sample_id,
        split="test",
        sample_origin="event_selected",
        anchor_adjustment="none",
        text="뉴스",
        beta=1.0,
        turnover_zscore=1.0,
        abnormal_return_std=std,
        surge_label=surge,
    )
