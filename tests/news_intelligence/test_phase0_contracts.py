from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from modules.adapters.brokers.kiwoom.news_intelligence import (
    normalize_minute_candles,
)
from modules.brokers.kiwoom.models.ohlcv import ChartBar
from modules.domain.news_intelligence import (
    KST,
    CatalogAlias,
    CatalogSecurity,
    CatalogSnapshot,
    HistoricalNameStatus,
    approved_kiwoom_benchmark,
    build_discovery_plan,
    candle_identity_checksum,
)


def test_kiwoom_minute_rows_become_aware_ordered_deduplicated_candles() -> None:
    bars = [
        _bar("2026-06-17 09:31:00"),
        _bar("2026-06-17 09:30:00"),
        _bar("2026-06-17 09:30:00", raw={"different": "transport-only"}),
    ]

    candles = normalize_minute_candles(
        bars,
        window_start=datetime(2026, 6, 17, 9, 30, tzinfo=KST),
        window_end=datetime(2026, 6, 17, 9, 31, tzinfo=KST),
    )

    assert [candle.timestamp.isoformat() for candle in candles] == [
        "2026-06-17T09:30:00+09:00",
        "2026-06-17T09:31:00+09:00",
    ]
    assert candle_identity_checksum(candles) == candle_identity_checksum(tuple(candles))


def test_kiwoom_normalization_rejects_out_of_range_and_conflicting_duplicates() -> None:
    start = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    end = datetime(2026, 6, 17, 9, 31, tzinfo=KST)

    with pytest.raises(ValueError, match="outside"):
        normalize_minute_candles(
            [_bar("2026-06-17 09:29:00")],
            window_start=start,
            window_end=end,
        )

    with pytest.raises(ValueError, match="conflicting duplicate"):
        normalize_minute_candles(
            [
                _bar("2026-06-17 09:30:00"),
                _bar("2026-06-17 09:30:00", close=Decimal("106")),
            ],
            window_start=start,
            window_end=end,
        )


def test_discovery_plan_emits_exact_alias_by_provider_date_matrix() -> None:
    aliases = (
        _alias("alias-samsung", " 삼성전자 "),
        _alias("alias-samsung-duplicate", "삼성전자"),
        _alias("alias-galaxy", "갤럭시"),
    )

    plan = build_discovery_plan(
        window_start=datetime(2026, 6, 17, 9, 30, tzinfo=KST),
        window_end=datetime(2026, 6, 17, 10, 30, tzinfo=KST),
        aliases=aliases,
    )

    assert plan.version == "naver-discovery-plan-v1"
    assert plan.offset_min_minutes == -720
    assert plan.offset_max_minutes == 840
    assert [
        (call.ordinal, call.alias_id, call.query, call.provider_date)
        for call in plan.calls
    ] == [
        (1, "alias-galaxy", "갤럭시", date(2026, 6, 16)),
        (2, "alias-galaxy", "갤럭시", date(2026, 6, 17)),
        (3, "alias-samsung", "삼성전자", date(2026, 6, 16)),
        (4, "alias-samsung", "삼성전자", date(2026, 6, 17)),
    ]


def test_catalog_snapshot_uses_persisted_acquisition_time_and_valid_aliases() -> None:
    snapshot = CatalogSnapshot(
        snapshot_id="catalog-20260617",
        version="catalog-v1",
        source="kis-domestic-symbols",
        acquired_at=datetime(2026, 6, 17, 8, 0, tzinfo=KST),
        checksum="sha256:catalog",
        securities=(
            CatalogSecurity(
                security_id="KRX:005930",
                market="KOSPI",
                symbol="005930",
                display_name="삼성전자",
                aliases=(
                    _alias("official-current", "삼성전자"),
                    CatalogAlias(
                        alias_id="historical-configured",
                        term="삼성전자공업",
                        valid_from=date(1969, 1, 1),
                        valid_to=date(1984, 12, 31),
                        source="configured-curation",
                        historical_name_status=HistoricalNameStatus.VALIDITY_RANGED,
                    ),
                ),
            ),
        ),
    )

    assert snapshot.is_stale(
        now=datetime(2026, 6, 19, 8, 1, tzinfo=KST),
        max_age=timedelta(days=2),
    )
    aliases = snapshot.securities[0].terms_on(date(1980, 1, 1))
    assert [alias.alias_id for alias in aliases] == ["historical-configured"]
    assert snapshot.securities[0].aliases[0].historical_name_status == "current_only"


@pytest.mark.parametrize(
    ("market", "name", "code"),
    [("KOSPI", "KOSPI", "001"), ("KOSDAQ", "KOSDAQ", "101")],
)
def test_benchmark_source_is_explicitly_owned_by_market(
    market: str, name: str, code: str
) -> None:
    proof = approved_kiwoom_benchmark(market)

    assert (proof.benchmark_name, proof.benchmark_code) == (name, code)
    assert (proof.api_id, proof.endpoint_path, proof.response_key) == (
        "ka20005",
        "/api/dostk/chart",
        "inds_min_pole_qry",
    )


def test_benchmark_source_rejects_unapproved_market() -> None:
    with pytest.raises(ValueError, match="no approved"):
        approved_kiwoom_benchmark("KONEX")


def _alias(alias_id: str, term: str) -> CatalogAlias:
    return CatalogAlias(
        alias_id=alias_id,
        term=term,
        valid_from=date(2026, 1, 1),
        valid_to=None,
        source="kis-current",
        historical_name_status=HistoricalNameStatus.CURRENT_ONLY,
    )


def _bar(
    timestamp: str,
    *,
    close: Decimal = Decimal("105"),
    raw: dict[str, str] | None = None,
) -> ChartBar:
    return ChartBar(
        market="KRX",
        symbol="005930",
        interval="1min",
        timestamp=timestamp,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=close,
        volume=1_000,
        raw=raw or {},
    )
