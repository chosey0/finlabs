from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
import json

import pytest
from fastapi.testclient import TestClient

from finlabs_intelligence.api.app import app
from modules.domain.news_intelligence import (
    KST,
    NewsArticleCandidate,
    NewsDiscoveryIncompleteError,
)
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.catalog import load_catalog_snapshot
from modules.storage.news_intelligence.repositories import load_sample
from modules.storage.news_intelligence.writer import SingleWriter
from tests.news_intelligence.test_discovery_slice import (
    _FakeMinuteMarketData,
    _catalog_database,
)


def test_discovery_executes_cross_offset_plan_and_keeps_inclusive_kst_boundaries(
    intelligence_dsn: str,
) -> None:
    news_search = _FakeNewsSearch()
    writer = SingleWriter(intelligence_dsn)
    services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        news_search=news_search,
        annotation_writer=writer,
    )

    result = _run_discovery(services)

    assert result.complete is True
    assert result.plan.expected_call_count == 4
    assert result.executed_call_count == 4
    assert [call.provider_date for call in result.plan.calls] == [
        date(2026, 6, 16),
        date(2026, 6, 17),
        date(2026, 6, 16),
        date(2026, 6, 17),
    ]
    assert [article.title for article in result.articles] == ["lower", "upper"]
    assert result.articles[0].published_at == datetime(2026, 6, 17, 8, 31, tzinfo=KST)
    assert result.articles[1].published_at == datetime(2026, 6, 17, 9, 31, tzinfo=KST)
    assert len(result.articles[0].matched_alias_ids) == 2
    sample = writer.read(
        lambda connection: load_sample(
            connection, sample_id=result.articles[0].sample_id
        )
    )
    assert sample is not None
    provenance = json.loads(sample.provenance_json)
    assert provenance["contributing_calls"]
    assert provenance["discovery_plan"]["expected_call_count"] == 4
    assert len(provenance["discovery_plan"]["calls"]) == 4
    assert {"ordinal", "alias_id", "query", "provider_date"} <= provenance[
        "contributing_calls"
    ][0].keys()


def test_rediscovery_from_another_selected_candle_reuses_sample_identity(
    intelligence_dsn: str,
) -> None:
    writer = SingleWriter(intelligence_dsn)
    services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        news_search=_FakeNewsSearch(),
        annotation_writer=writer,
    )

    first = _run_discovery(services)
    annotation = asyncio.run(
        services.save_annotation(
            idempotency_key="annotation-before-rediscovery",
            sample_id=next(
                article.sample_id
                for article in first.articles
                if article.title == "upper"
            ),
            final_value="relevant",
            actor="reviewer",
            note=None,
            annotation_id="annotation-before-rediscovery",
        )
    )
    second = asyncio.run(
        services.discover_news(
            security_id="KOSDAQ:123456",
            selected_candle_at=datetime(2026, 6, 17, 9, 32, tzinfo=KST),
        )
    )

    first_upper = next(
        article for article in first.articles if article.title == "upper"
    )
    second_upper = next(
        article for article in second.articles if article.title == "upper"
    )
    assert first_upper.sample_id == second_upper.sample_id
    count = writer.read(
        lambda connection: connection.execute(
            "SELECT COUNT(*) FROM intelligence_samples"
        ).fetchone()[0]
    )
    assert count == 2
    frozen = asyncio.run(
        services.freeze_dataset(
            idempotency_key="freeze-after-rediscovery",
            dataset_id="rediscovery-provenance",
            purpose="relevance_training",
            cohort="historical_publication_proxy",
            annotation_ids=(annotation.annotation_id,),
        )
    )
    assert frozen.snapshot.members[0]["provenance"]["selected_candle_at"] == (
        "2026-06-17T09:31:00+09:00"
    )


def test_discovery_never_returns_partial_results_when_a_planned_call_fails(
    intelligence_dsn: str,
) -> None:
    services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        news_search=_IncompleteNewsSearch(),
    )

    with pytest.raises(NewsDiscoveryIncompleteError):
        _run_discovery(services)


def test_news_discovery_route_exposes_frozen_plan_and_complete_result(
    intelligence_dsn: str,
) -> None:
    app.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        news_search=_FakeNewsSearch(),
    )

    response = TestClient(app).post(
        "/api/news/discover",
        json={
            "security_id": "KOSDAQ:123456",
            "selected_candle_at": "2026-06-17T09:31:00+09:00",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_start"] == "2026-06-17T08:31:00+09:00"
    assert payload["window_end"] == "2026-06-17T09:31:00+09:00"
    assert payload["expected_call_count"] == payload["executed_call_count"] == 4
    assert payload["complete"] is True
    assert len(payload["calls"]) == 4
    assert len(payload["articles"]) == 2


def test_discovery_honors_an_explicit_earlier_window_start(
    intelligence_dsn: str,
) -> None:
    services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        news_search=_FakeNewsSearch(),
    )

    result = asyncio.run(
        services.discover_news(
            security_id="KOSDAQ:123456",
            selected_candle_at=datetime(2026, 6, 17, 9, 31, tzinfo=KST),
            window_start=datetime(2026, 6, 17, 8, 30, tzinfo=KST),
        )
    )

    # The 08:30:59 article fell outside the default prior-hour window; widening
    # the start to 08:30 pulls it in, while t0 (the anchor) stays at 09:31.
    assert result.plan.window_start == datetime(2026, 6, 17, 8, 30, tzinfo=KST)
    assert result.plan.window_end == datetime(2026, 6, 17, 9, 31, tzinfo=KST)
    assert result.selected_candle_at == datetime(2026, 6, 17, 9, 31, tzinfo=KST)
    assert [article.title for article in result.articles] == [
        "outside",
        "lower",
        "upper",
    ]


def test_discovery_rejects_a_window_start_at_or_after_the_anchor(
    intelligence_dsn: str,
) -> None:
    app.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        news_search=_FakeNewsSearch(),
    )

    response = TestClient(app).post(
        "/api/news/discover",
        json={
            "security_id": "KOSDAQ:123456",
            "selected_candle_at": "2026-06-17T09:31:00+09:00",
            "window_start": "2026-06-17T09:31:00+09:00",
        },
    )

    assert response.status_code == 422
    assert response.json()["message"] == (
        "window_start must be before selected_candle_at"
    )


def _run_discovery(services: NewsIntelligenceServices):
    import asyncio

    return asyncio.run(
        services.discover_news(
            security_id="KOSDAQ:123456",
            selected_candle_at=datetime(2026, 6, 17, 9, 31, tzinfo=KST),
        )
    )


class _FakeNewsSearch:
    def search_date(
        self,
        *,
        keyword: str,
        provider_date: date,
    ) -> tuple[NewsArticleCandidate, ...]:
        del provider_date
        return (
            _article("lower", datetime(2026, 6, 17, 8, 31, tzinfo=KST)),
            _article(
                "upper",
                datetime(2026, 6, 16, 17, 31, tzinfo=timezone(timedelta(hours=-7))),
            ),
            _article("outside", datetime(2026, 6, 17, 8, 30, 59, tzinfo=KST)),
        )


class _IncompleteNewsSearch:
    calls = 0

    def search_date(
        self,
        *,
        keyword: str,
        provider_date: date,
    ) -> tuple[NewsArticleCandidate, ...]:
        del keyword, provider_date
        self.calls += 1
        if self.calls == 2:
            raise NewsDiscoveryIncompleteError("pagination cap")
        return ()


def _article(title: str, published_at: datetime) -> NewsArticleCandidate:
    canonical_url = f"https://publisher.example/{title}"
    return NewsArticleCandidate(
        title=title,
        description=f"{title} description",
        published_at=published_at,
        original_url=canonical_url,
        naver_url=f"https://n.news.naver.com/{title}",
    )
