from __future__ import annotations

from datetime import datetime, timedelta

from modules.domain.news_intelligence import KST
from modules.news.intelligence.modeling.dataset import (
    SurgeSample,
    load_surge_samples,
    partition,
)
from modules.news.intelligence.modeling.features import HashingTextEmbedder
from modules.news.intelligence.modeling.model import RidgeRegressor
from modules.news.intelligence.modeling.pipeline import train_and_evaluate


def test_load_surge_samples_parses_member_strings() -> None:
    snapshot = {
        "members": [
            {
                "sample_id": "s1",
                "security_id": "KOSDAQ:123456",
                "market": "KOSDAQ",
                "effective_label_anchor": "2026-06-17T09:30:00+09:00",
                "event_id": "e1",
                "split": "train",
                "sample_origin": "event_selected",
                "abnormal_return_std": "2.5",
                "turnover_zscore": "1.3",
                "beta": "1.1",
                "surge_label": 1,
                "title": "테스트기업 급등",
                "description": "공급 계약",
                "provenance": {"reaction": {"anchor_adjustment": "rolled_to_next_session"}},
            }
        ]
    }

    (sample,) = load_surge_samples(snapshot)

    assert sample.abnormal_return_std == 2.5
    assert sample.turnover_zscore == 1.3
    assert sample.anchor_adjustment == "rolled_to_next_session"
    assert sample.has_regression_target
    assert "급등" in sample.text


def test_partition_holds_out_latest_events_without_leakage() -> None:
    base = datetime(2026, 6, 1, 9, 30, tzinfo=KST)
    rows = tuple(
        _sample(f"s{i}", base + timedelta(days=i), event=f"e{i}", split="train")
        for i in range(10)
    )

    splits = partition(rows, out_of_time_fraction=0.3)

    assert len(splits.out_of_time_test) == 3  # int(10 * 0.3)
    oot_events = {row.event_id for row in splits.out_of_time_test}
    in_time_events = {
        row.event_id
        for row in splits.train + splits.validation + splits.iid_test
    }
    assert oot_events.isdisjoint(in_time_events)  # no event straddles the cut
    latest_in_time = max(row.anchor for row in splits.train)
    earliest_oot = min(row.anchor for row in splits.out_of_time_test)
    assert earliest_oot > latest_in_time  # forward-in-time holdout


def test_pipeline_trains_and_ranks_a_linear_signal() -> None:
    base = datetime(2026, 3, 2, 9, 30, tzinfo=KST)  # a Monday
    rows = []
    for i in range(40):
        turnover = (i % 7) - 3  # spread of z-scores
        std = 0.8 * turnover  # deterministic linear signal
        rows.append(
            _sample(
                f"s{i}",
                base + timedelta(days=i),
                event=f"e{i}",
                split=("validation" if i % 5 == 3 else "test" if i % 5 == 4 else "train"),
                turnover=float(turnover),
                std=std,
                surge=1 if std >= 2 else 0,
            )
        )

    report = train_and_evaluate(
        rows,
        embedder=HashingTextEmbedder(dimension=16),
        model_factory=lambda: RidgeRegressor(alpha=0.1),
        k=3,
        out_of_time_fraction=0.25,
    )

    assert report.n_train > 0
    assert report.out_of_time_test.n == 10  # int(40 * 0.25)
    # The model recovers the turnover -> std signal, so out-of-time ranking is
    # positively correlated and beats the constant baseline.
    assert report.out_of_time_test.spearman > 0.5
    assert report.out_of_time_test.spearman > report.baselines["constant"].spearman
    assert "origin:event_selected" in report.slices


def _sample(
    sample_id: str,
    anchor: datetime,
    *,
    event: str,
    split: str,
    turnover: float = 1.0,
    std: float = 1.0,
    surge: int = 0,
) -> SurgeSample:
    return SurgeSample(
        sample_id=sample_id,
        security_id=f"KOSDAQ:{sample_id}",
        market="KOSDAQ",
        anchor=anchor,
        event_id=event,
        split=split,
        sample_origin="event_selected",
        anchor_adjustment="none",
        text="뉴스",
        beta=1.0,
        turnover_zscore=turnover,
        abnormal_return_std=std,
        surge_label=surge,
    )
