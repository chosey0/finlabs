from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from finlabs_intelligence.api.app import app
from modules.domain.news_intelligence import KST
from modules.news.intelligence.processors.reaction import MarketPoint, preview_reaction
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.catalog import load_catalog_snapshot
from modules.storage.news_intelligence.repositories import SampleRecord, upsert_sample
from modules.storage.news_intelligence.writer import SingleWriter
import json
from datetime import timezone
from tests.news_intelligence.test_discovery_slice import (
    _FakeMinuteMarketData,
    _catalog_database,
)


def test_reaction_uses_exact_30th_trading_minute_and_only_pre_anchor_features() -> None:
    start = datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    session = tuple(start + timedelta(minutes=index) for index in range(80))
    anchor = session[30]
    stock = tuple(
        MarketPoint(
            timestamp=timestamp,
            close=Decimal("100") if timestamp <= anchor else Decimal("103"),
            turnover=Decimal(index + 1),
        )
        for index, timestamp in enumerate(session)
    )
    benchmark = tuple(
        MarketPoint(
            timestamp=timestamp,
            close=Decimal("100") if timestamp <= anchor else Decimal("101"),
            turnover=Decimal("1"),
        )
        for timestamp in session
    )

    result = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=stock,
        benchmark_points=benchmark,
        session_minutes=session,
    )

    assert result.label_window_end == session[60]
    assert result.feature_cutoff_at == anchor
    assert result.abnormal_return == Decimal("0.02")
    assert result.reaction_class == "positive"
    assert result.exclusion_reason is None


def test_reaction_rolls_after_hours_anchor_to_next_session_open() -> None:
    from datetime import date

    from modules.news.intelligence.processors.session_grid import (
        regular_session_minutes,
    )

    grid = regular_session_minutes([date(2026, 6, 17), date(2026, 6, 18)])
    anchor = datetime(2026, 6, 17, 16, 0, tzinfo=KST)  # after the 06-17 close
    next_open = datetime(2026, 6, 18, 9, 0, tzinfo=KST)

    # Stock/benchmark points: a short pre-open tail (for turnover history) plus the
    # required forward window at the next session open.
    covered = [grid[385 + index] for index in range(6)]  # 06-17 15:25..15:30
    covered += [next_open + timedelta(minutes=index) for index in range(31)]
    stock = tuple(
        MarketPoint(
            timestamp=ts,
            close=Decimal("100") if ts <= next_open else Decimal("103"),
            turnover=Decimal(index + 1),
        )
        for index, ts in enumerate(covered)
    )
    benchmark = tuple(
        MarketPoint(
            timestamp=ts,
            close=Decimal("100") if ts <= next_open else Decimal("101"),
            turnover=Decimal("1"),
        )
        for ts in covered
    )

    result = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=stock,
        benchmark_points=benchmark,
        session_minutes=grid,
    )

    assert result.exclusion_reason is None
    assert result.anchor_adjustment == "rolled_to_next_session"
    assert result.feature_cutoff_at == anchor  # information time is unchanged
    assert result.label_window_start == next_open
    assert result.label_window_end == next_open + timedelta(minutes=30)
    assert result.abnormal_return == Decimal("0.02")
    assert result.pre_anchor_drift is None  # not meaningful for a rolled anchor


def test_reaction_flags_pre_anchor_drift_for_in_session_anchor() -> None:
    start = datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    session = tuple(start + timedelta(minutes=index) for index in range(80))
    anchor = session[30]  # 09:30, in session
    pre = session[25]  # 09:25, five minutes earlier
    # Stock jumps in the five minutes before the anchor (timestamp lagging event).
    stock = tuple(
        MarketPoint(
            timestamp=ts,
            close=Decimal("105") if ts >= anchor else Decimal("100"),
            turnover=Decimal(index + 1),
        )
        for index, ts in enumerate(session)
    )
    benchmark = tuple(
        MarketPoint(timestamp=ts, close=Decimal("100"), turnover=Decimal("1"))
        for ts in session
    )

    result = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=stock,
        benchmark_points=benchmark,
        session_minutes=session,
    )

    assert result.anchor_adjustment == "none"
    assert pre in {point.timestamp for point in stock}
    assert result.pre_anchor_abnormal_return == Decimal("0.05")
    assert result.pre_anchor_drift is True


def test_reaction_estimates_beta_and_standardizes_abnormal_return() -> None:
    start = datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    session = tuple(start + timedelta(minutes=index) for index in range(80))
    anchor = session[30]
    # Flat benchmark -> beta falls back to 1; stock has pre-anchor variance so the
    # abnormal-return volatility (denominator) is non-zero and standardization runs.
    stock = tuple(
        MarketPoint(
            timestamp=ts,
            close=(
                Decimal("105")
                if ts > anchor
                else Decimal("100") + (index % 2)  # alternates 100/101 pre-anchor
            ),
            turnover=Decimal(index + 1),
        )
        for index, ts in enumerate(session)
    )
    benchmark = tuple(
        MarketPoint(timestamp=ts, close=Decimal("100"), turnover=Decimal("1"))
        for ts in session
    )

    result = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=stock,
        benchmark_points=benchmark,
        session_minutes=session,
    )

    assert result.exclusion_reason is None
    assert result.beta == Decimal("1")  # zero-variance benchmark -> fallback
    assert result.abnormal_return == Decimal("0.05")  # 105/100 - 1, flat benchmark
    assert result.abnormal_return_std is not None  # standardized primary target


def test_reaction_rejects_a_horizon_with_missing_intermediate_minutes() -> None:
    anchor = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    session = tuple(anchor + timedelta(minutes=index) for index in range(31))
    points = tuple(
        MarketPoint(timestamp=value, close=Decimal("100"), turnover=Decimal(index + 1))
        for index, value in enumerate(session)
        if index != 12
    )
    result = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=points,
        benchmark_points=tuple(
            MarketPoint(timestamp=value, close=Decimal("100"), turnover=Decimal("1"))
            for value in session
        ),
        session_minutes=session,
    )
    assert result.exclusion_reason == "incomplete_stock_window"


@pytest.mark.parametrize(
    ("benchmark", "session", "reason"),
    [
        (None, "present", "benchmark_unavailable"),
        ("present", None, "session_calendar_unavailable"),
    ],
)
def test_reaction_fails_closed_without_required_point_in_time_sources(
    benchmark: str | None,
    session: str | None,
    reason: str,
) -> None:
    anchor = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    minutes = tuple(anchor + timedelta(minutes=index) for index in range(31))
    points = tuple(
        MarketPoint(timestamp=value, close=Decimal("100"), turnover=Decimal("1"))
        for value in minutes
    )

    result = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=points,
        benchmark_points=points if benchmark else None,
        session_minutes=minutes if session else None,
    )

    assert result.exclusion_reason == reason
    assert result.reaction_class is None
    assert result.is_strong_reaction is None


def test_preview_api_exposes_anchor_basis_cohort_and_typed_exclusion(
    intelligence_dsn: str,
) -> None:
    writer = SingleWriter(intelligence_dsn)
    anchor = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    writer.execute(
        lambda connection: upsert_sample(
            connection,
            sample=SampleRecord(
                sample_id="sample-reaction",
                article_id="article-reaction",
                security_id="KOSDAQ:123456",
                market="KOSDAQ",
                symbol="123456",
                title="테스트기업",
                description="뉴스",
                published_at=anchor,
                effective_label_anchor=anchor,
                anchor_basis="published_at_proxy",
                cohort="historical_publication_proxy",
                provenance_json=json.dumps({}),
                reaction_class=None,
                reaction_exclusion_reason="benchmark_unavailable",
            ),
            created_at=datetime.now(timezone.utc),
        )
    )
    app.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        annotation_writer=writer,
    )
    response = TestClient(app).post(
        "/api/datasets/preview",
        json={
            "sample_id": "sample-reaction",
        },
    )

    assert response.status_code == 200
    assert response.json()["exclusion_reason"] == "benchmark_unavailable"
    assert response.json()["reaction_class"] is None
    assert response.json()["cohort"] == "historical_publication_proxy"
    assert response.json()["effective_label_anchor"] == "2026-06-17T09:30:00+09:00"
