"""Run the real FastAPI app with deterministic local E2E ports and temp storage."""

from __future__ import annotations

import tempfile
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import uvicorn
from fastapi.middleware.cors import CORSMiddleware

from finlabs_intelligence.api.app import app
from modules.domain.news_intelligence import (
    CatalogAlias,
    CatalogSecurity,
    CatalogSnapshot,
    HistoricalNameStatus,
    IntelligenceCandle,
    KST,
    NewsArticleCandidate,
    ReactionMarketPoint,
    ReactionSourceData,
    approved_kiwoom_benchmark,
)
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.writer import SingleWriter


class E2EMarketData:
    async def validate_symbol(self, *, market: str, symbol: str) -> None:
        if (market, symbol) != ("KOSDAQ", "123456"):
            raise ValueError("unknown E2E security")

    async def minute_bars(
        self,
        *,
        market: str,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[IntelligenceCandle, ...]:
        del window_start, window_end
        return tuple(
            IntelligenceCandle(
                market=market,
                symbol=symbol,
                interval="1min",
                timestamp=datetime(2026, 6, 17, 9, minute, tzinfo=KST),
                open=Decimal("100") + minute,
                high=Decimal("102") + minute,
                low=Decimal("99") + minute,
                close=Decimal("101") + minute,
                volume=100 + minute,
            )
            for minute in (30, 31)
        )


class E2ENewsSearch:
    def search_date(
        self, *, keyword: str, provider_date: date
    ) -> tuple[NewsArticleCandidate, ...]:
        del keyword, provider_date
        return (
            NewsArticleCandidate(
                title="테스트기업 계약",
                description="테스트기업이 공급 계약을 체결했다.",
                published_at=datetime(2026, 6, 17, 9, 10, tzinfo=KST),
                original_url="https://publisher.example/e2e-article",
                naver_url="https://n.news.naver.com/e2e-article",
            ),
        )


class E2EReactionData:
    async def reaction_data(
        self,
        *,
        market: str,
        symbol: str,
        effective_label_anchor: datetime,
    ) -> ReactionSourceData:
        del symbol
        start = effective_label_anchor - timedelta(minutes=20)
        minutes = tuple(start + timedelta(minutes=index) for index in range(51))
        stock = tuple(
            ReactionMarketPoint(
                timestamp=timestamp,
                close=Decimal("100") + index,
                turnover=Decimal(index + 1),
            )
            for index, timestamp in enumerate(minutes)
        )
        benchmark = tuple(
            ReactionMarketPoint(
                timestamp=timestamp,
                close=Decimal("100") + Decimal(index) / 10,
                turnover=Decimal("1"),
            )
            for index, timestamp in enumerate(minutes)
        )
        return ReactionSourceData(
            stock_points=stock,
            benchmark_points=benchmark,
            session_minutes=minutes,
            benchmark_proof=approved_kiwoom_benchmark(market),
            session_id="e2e-session-2026-06-17",
            source_checksum="e2e-source-checksum",
        )


def _catalog() -> CatalogSnapshot:
    alias = CatalogAlias(
        alias_id="official",
        term="테스트기업",
        valid_from=date(2020, 1, 1),
        valid_to=None,
        source="e2e-fixture",
        historical_name_status=HistoricalNameStatus.CURRENT_ONLY,
    )
    return CatalogSnapshot(
        snapshot_id="e2e-catalog",
        version="e2e-v1",
        source="kis-domestic-symbol-master",
        acquired_at=datetime(2026, 6, 17, 8, tzinfo=KST),
        checksum="e2e-catalog-checksum",
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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="finlabs-intelligence-e2e-") as root:
        app.state.news_intelligence_services = NewsIntelligenceServices(
            catalog_snapshot=_catalog(),
            market_data=E2EMarketData(),
            news_search=E2ENewsSearch(),
            annotation_writer=SingleWriter(),
            export_root=Path(root) / "exports",
            reaction_data=E2EReactionData(),
        )
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://127.0.0.1:42817"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
        uvicorn.run(app, host="127.0.0.1", port=42818, log_level="warning")


if __name__ == "__main__":
    main()
