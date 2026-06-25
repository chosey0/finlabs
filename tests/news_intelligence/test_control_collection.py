from __future__ import annotations

import asyncio
from datetime import date, datetime

from modules.domain.news_intelligence import (
    KST,
    CatalogAlias,
    CatalogSecurity,
    CatalogSnapshot,
    HistoricalNameStatus,
    NewsArticleCandidate,
)
from modules.news.intelligence.processors.session_grid import weekday_trading_sessions
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.repositories import load_sample
from modules.storage.news_intelligence.writer import SingleWriter
from tests.news_intelligence.test_discovery_slice import _FakeMinuteMarketData


def test_weekday_trading_sessions_skip_weekends() -> None:
    # 2026-06-17 is a Wednesday; the range spans through the weekend.
    sessions = weekday_trading_sessions(date(2026, 6, 17), date(2026, 6, 22))

    session_ids = [session_id for session_id, _ in sessions]
    assert session_ids == ["2026-06-17", "2026-06-18", "2026-06-19", "2026-06-22"]
    assert all(len(minutes) == 391 for _, minutes in sessions)  # 09:00..15:30


def test_collect_control_samples_persists_random_control_origin(
    intelligence_dsn: str,
) -> None:
    anchor = datetime(2026, 6, 17, 10, 30, tzinfo=KST)
    article = NewsArticleCandidate(
        title="테스트기업 공급계약",
        description="테스트기업이 계약을 체결했다.",
        published_at=datetime(2026, 6, 17, 10, 0, tzinfo=KST),
        original_url="https://publisher.example/control-article",
        naver_url="https://n.news.naver.com/control-article",
    )
    writer = SingleWriter(intelligence_dsn)
    services = NewsIntelligenceServices(
        catalog_snapshot=_catalog(),
        market_data=_FakeMinuteMarketData(),
        news_search=_FakeNewsSearch(article),
        annotation_writer=writer,
    )

    result = asyncio.run(
        services.collect_control_samples(
            securities=("KOSDAQ:123456",),
            sessions=(("2026-06-17", (anchor,)),),  # single minute -> deterministic
            seed="control-seed",
            per_session=1,
        )
    )

    assert result.planned == 1
    assert result.skipped == 0
    assert len(result.sample_ids) >= 1
    sample = writer.read(
        lambda connection: load_sample(connection, sample_id=result.sample_ids[0])
    )
    assert sample is not None
    assert sample.sample_origin == "random_control"


def test_collect_control_samples_skips_unknown_security(
    intelligence_dsn: str,
) -> None:
    anchor = datetime(2026, 6, 17, 10, 30, tzinfo=KST)
    services = NewsIntelligenceServices(
        catalog_snapshot=_catalog(),
        market_data=_FakeMinuteMarketData(),
        news_search=_FakeNewsSearch(None),
        annotation_writer=SingleWriter(intelligence_dsn),
    )

    result = asyncio.run(
        services.collect_control_samples(
            securities=("KOSDAQ:999999",),  # not in the catalog
            sessions=(("2026-06-17", (anchor,)),),
            seed="control-seed",
        )
    )

    assert result.planned == 1
    assert result.skipped == 1
    assert result.sample_ids == ()


class _FakeNewsSearch:
    def __init__(self, article: NewsArticleCandidate | None) -> None:
        self._article = article

    def search_date(self, *, keyword: str, provider_date: date):
        del keyword, provider_date
        return (self._article,) if self._article is not None else ()


def _catalog() -> CatalogSnapshot:
    alias = CatalogAlias(
        alias_id="official",
        term="테스트기업",
        valid_from=date(2026, 1, 1),
        valid_to=None,
        source="test",
        historical_name_status=HistoricalNameStatus.CURRENT_ONLY,
    )
    return CatalogSnapshot(
        snapshot_id="catalog-control",
        version="v1",
        source="test",
        acquired_at=datetime(2026, 6, 17, 8, tzinfo=KST),
        checksum="checksum",
        securities=(
            CatalogSecurity(
                security_id="KOSDAQ:123456",
                market="KOSDAQ",
                symbol="123456",
                display_name="테스트기업",
                aliases=(alias,),
            ),
        ),
    )
