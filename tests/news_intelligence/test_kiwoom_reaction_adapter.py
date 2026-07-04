from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

from modules.adapters.brokers.kiwoom.reaction_data import KiwoomReactionMarketData
from brokers.kiwoom.models.ohlcv import ChartBar
from modules.domain.news_intelligence import KST, approved_kiwoom_benchmark
from modules.news.intelligence.processors.reaction import preview_reaction


def test_kiwoom_reaction_adapter_loads_approved_aligned_benchmark() -> None:
    anchor = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    chart = _FakeChart(anchor)
    client = SimpleNamespace(domestic=SimpleNamespace(chart=chart))

    result = asyncio.run(
        KiwoomReactionMarketData(client).reaction_data(
            market="KOSDAQ",
            symbol="123456",
            effective_label_anchor=anchor,
        )
    )

    assert result.benchmark_proof == approved_kiwoom_benchmark("KOSDAQ")
    assert chart.industry_code == "101"
    # session_minutes is now the real KRX regular-session grid for the trading
    # date(s) the stock actually traded, not a fabricated anchor..+30 stub.
    assert result.session_minutes[0] == datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    assert result.session_minutes[-1] == datetime(2026, 6, 17, 15, 30, tzinfo=KST)
    assert len(result.session_minutes) == 391
    assert anchor in result.session_minutes
    assert anchor + timedelta(minutes=30) in result.session_minutes
    assert len(result.stock_points) == len(result.benchmark_points) == 51
    assert len(result.source_checksum) == 64


def test_kiwoom_reaction_adapter_does_not_hide_missing_benchmark_minute() -> None:
    anchor = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    chart = _FakeChart(anchor, missing_benchmark_index=30)
    client = SimpleNamespace(domestic=SimpleNamespace(chart=chart))

    source = asyncio.run(
        KiwoomReactionMarketData(client).reaction_data(
            market="KOSDAQ",
            symbol="123456",
            effective_label_anchor=anchor,
        )
    )
    preview = preview_reaction(
        effective_label_anchor=anchor,
        stock_points=source.stock_points,
        benchmark_points=source.benchmark_points,
        session_minutes=source.session_minutes,
    )

    assert preview.exclusion_reason == "incomplete_benchmark_window"


class _FakeChart:
    def __init__(
        self, anchor: datetime, missing_benchmark_index: int | None = None
    ) -> None:
        self.anchor = anchor
        self.industry_code = ""
        self.missing_benchmark_index = missing_benchmark_index

    async def minute(self, symbol: str, **kwargs) -> list[ChartBar]:
        del kwargs
        return _bars(symbol, self.anchor, close_step=Decimal("1"))

    async def industry_minute(self, index_code: str, **kwargs) -> list[ChartBar]:
        del kwargs
        self.industry_code = index_code
        bars = _bars(index_code, self.anchor, close_step=Decimal("0.1"))
        if self.missing_benchmark_index is not None:
            bars.pop(self.missing_benchmark_index)
        return bars


def _bars(symbol: str, anchor: datetime, *, close_step: Decimal) -> list[ChartBar]:
    start = anchor - timedelta(minutes=20)
    return [
        ChartBar(
            market="KRX",
            symbol=symbol,
            interval="1min",
            timestamp=(start + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S"),
            open=Decimal("100"),
            high=Decimal("110"),
            low=Decimal("90"),
            close=Decimal("100") + close_step * index,
            volume=100 + index,
            amount=None,
        )
        for index in range(51)
    ]
