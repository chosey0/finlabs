from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import psycopg
from fastapi.testclient import TestClient

from finlabs_intelligence.api.app import app
from brokers.kiwoom.models.ohlcv import ChartBar
from modules.adapters.brokers.kiwoom.news_intelligence import normalize_chart_candles
from modules.domain.news_intelligence import (
    KST,
    IntelligenceCandle,
    MarketDataProviderError,
)
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.catalog import (
    load_catalog_snapshot,
    search_catalog,
)


def test_catalog_search_disambiguates_duplicate_names_and_freezes_snapshot(
    intelligence_dsn: str,
) -> None:
    database = _catalog_database(intelligence_dsn)
    snapshot = load_catalog_snapshot(database)

    matches = search_catalog(snapshot, "테스트기업")

    assert [(item.market, item.symbol) for item in matches] == [
        ("KOSDAQ", "123456"),
        ("KOSPI", "654321"),
    ]
    assert snapshot.snapshot_id.startswith("kis-domestic:")
    assert snapshot.acquired_at.isoformat() == "2026-06-17T08:00:00+09:00"
    assert all(
        alias.historical_name_status == "current_only"
        for item in matches
        for alias in item.aliases
    )


def test_catalog_chart_route_validates_with_kiwoom_and_returns_aware_ordered_bars(
    intelligence_dsn: str,
) -> None:
    # Seed a freshly-acquired catalog so the catalog_stale assertion below does
    # not depend on the wall clock (the route checks freshness against now).
    fresh = datetime.now(KST).replace(microsecond=0).isoformat()
    snapshot = load_catalog_snapshot(
        _catalog_database(intelligence_dsn, downloaded_at=fresh)
    )
    market_data = _FakeMinuteMarketData()
    app.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=snapshot,
        market_data=market_data,
    )
    client = TestClient(app)

    catalog_response = client.get("/api/catalog", params={"q": "123456"})
    chart_response = client.get(
        "/api/charts/123456",
        params={
            "market": "KOSDAQ",
            "start_at": "2026-06-17T09:30:00+09:00",
            "end_at": "2026-06-17T09:31:00+09:00",
        },
    )

    assert catalog_response.status_code == 200
    assert catalog_response.json()[0]["catalog_snapshot_id"] == snapshot.snapshot_id
    assert catalog_response.json()[0]["catalog_source"] == "kis-domestic-symbol-master"
    assert catalog_response.json()[0]["historical_name_status"] == "current_only"
    assert catalog_response.json()[0]["catalog_stale"] is False
    assert chart_response.status_code == 200
    payload = chart_response.json()
    assert payload["replayable"] is False
    assert [row["timestamp"] for row in payload["candles"]] == [
        "2026-06-17T09:30:00+09:00",
        "2026-06-17T09:31:00+09:00",
    ]
    assert market_data.validated == [("KOSDAQ", "123456")]


def test_api_errors_are_safe_structured_and_correlation_addressable() -> None:
    # Services must be present so the empty-`q` request reaches query validation
    # (an unconfigured app short-circuits with 503 before validation runs). The
    # request fails validation before the route body, so a sentinel is enough.
    app.state.news_intelligence_services = object()
    response = TestClient(app).get("/api/catalog", params={"q": ""})

    assert response.status_code == 422
    assert response.json()["code"] == "request_validation_failed"
    assert response.json()["retryable"] is False
    assert response.json()["details_safe"] == {"error_count": 1}
    assert len(response.json()["correlation_id"]) == 32


def test_market_provider_errors_use_safe_retryable_envelope(
    intelligence_dsn: str,
) -> None:
    app.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FailingMarketData(),
    )
    response = TestClient(app).get(
        "/api/charts/123456",
        params={
            "market": "KOSDAQ",
            "start_at": "2026-06-17T09:30:00+09:00",
            "end_at": "2026-06-17T09:31:00+09:00",
        },
    )

    assert response.status_code == 502
    assert response.json()["retryable"] is True
    assert response.json()["message"] == "Kiwoom market data request failed"


class _FailingMarketData:
    async def validate_symbol(self, *, market: str, symbol: str) -> None:
        del market, symbol
        raise MarketDataProviderError("Kiwoom market data request failed")

    async def chart_bars(self, **kwargs):
        del kwargs
        raise AssertionError("unreachable")


class _FakeMinuteMarketData:
    def __init__(self) -> None:
        self.validated: list[tuple[str, str]] = []

    async def validate_symbol(self, *, market: str, symbol: str) -> None:
        self.validated.append((market, symbol))

    async def chart_bars(
        self,
        *,
        market: str,
        symbol: str,
        chart_type: str = "minute",
        interval_minutes: int = 1,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[IntelligenceCandle, ...]:
        del chart_type, interval_minutes
        return normalize_chart_candles(
            [
                _bar(symbol, "2026-06-17 09:31:00"),
                _bar(symbol, "2026-06-17 09:30:00"),
            ],
            window_start=window_start,
            window_end=window_end,
        )


def _catalog_database(
    dsn: str, *, downloaded_at: str = "2026-06-17T08:00:00+09:00"
) -> str:
    """Seed the shared two-row domestic catalog into the test's schema.

    Returns the same DSN so callers can pass it straight to
    ``load_catalog_snapshot``; the table lives in the search_path schema the
    ``intelligence_dsn`` fixture created. ``downloaded_at`` sets the catalog
    acquisition time; pass a recent value for staleness assertions that must not
    depend on the wall clock.
    """

    with psycopg.connect(dsn, autocommit=True) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS domestic_symbols (
                market VARCHAR,
                symbol VARCHAR,
                korean_name VARCHAR,
                english_name VARCHAR,
                security_type VARCHAR,
                downloaded_at VARCHAR
            )
            """
        )
        with connection.cursor() as cursor:
            cursor.executemany(
                "INSERT INTO domestic_symbols VALUES (%s, %s, %s, %s, %s, %s)",
                [
                    (
                        "KOSPI",
                        "654321",
                        "테스트기업",
                        "Test Corp",
                        "stock",
                        downloaded_at,
                    ),
                    (
                        "KOSDAQ",
                        "123456",
                        "테스트기업",
                        "Test Labs",
                        "stock",
                        downloaded_at,
                    ),
                ],
            )
    return dsn


def _bar(symbol: str, timestamp: str) -> ChartBar:
    return ChartBar(
        market="KRX",
        symbol=symbol,
        interval="1min",
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=1_000,
    )
