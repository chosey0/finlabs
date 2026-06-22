"""Kiwoom stock/index minute data for point-in-time reaction labels."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from modules.brokers.kiwoom.client import KiwoomClient
from modules.brokers.kiwoom.models.ohlcv import ChartBar
from modules.brokers.kiwoom.exceptions import KiwoomError
from modules.domain.news_intelligence import (
    KST,
    MarketDataProviderError,
    ReactionMarketPoint,
    ReactionSourceData,
    approved_kiwoom_benchmark,
)

_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S"


class KiwoomReactionMarketData:
    """Load aligned stock and approved benchmark minute series from Kiwoom."""

    def __init__(self, client: KiwoomClient) -> None:
        self._client = client

    async def reaction_data(
        self,
        *,
        market: str,
        symbol: str,
        effective_label_anchor: datetime,
    ) -> ReactionSourceData:
        if (
            effective_label_anchor.tzinfo is None
            or effective_label_anchor.utcoffset() is None
        ):
            raise ValueError("effective_label_anchor must be timezone-aware")
        anchor = effective_label_anchor.astimezone(KST).replace(second=0, microsecond=0)
        proof = approved_kiwoom_benchmark(market)
        window_start = anchor - timedelta(hours=2)
        window_end = anchor + timedelta(hours=2)
        start_date = window_start.strftime("%Y-%m-%d %H%M%S")

        try:
            stock_bars = await self._client.domestic.chart.minute(
                symbol,
                interval_minutes=1,
                base_date=window_end.date(),
                market="KRX",
                start_date=start_date,
            )
            benchmark_bars = await self._client.domestic.chart.industry_minute(
                proof.benchmark_code,
                interval_minutes=1,
                base_date=window_end.date(),
                start_date=start_date,
            )
        except KiwoomError as error:
            raise MarketDataProviderError(
                "Kiwoom reaction data request failed"
            ) from error
        stock_points = _points(stock_bars, window_start, window_end)
        benchmark_points = _points(benchmark_bars, window_start, window_end)
        session_minutes = tuple(
            anchor + timedelta(minutes=index) for index in range(31)
        )
        checksum = _source_checksum(stock_points, benchmark_points, proof.api_id)
        return ReactionSourceData(
            stock_points=stock_points,
            benchmark_points=benchmark_points,
            session_minutes=session_minutes,
            benchmark_proof=proof,
            session_id=f"kiwoom:{anchor.date().isoformat()}:{market}:1m",
            source_checksum=checksum,
        )


def _points(
    bars: list[ChartBar], window_start: datetime, window_end: datetime
) -> tuple[ReactionMarketPoint, ...]:
    points: dict[datetime, ReactionMarketPoint] = {}
    for bar in bars:
        if bar.interval != "1min":
            raise ValueError("reaction source requires one-minute bars")
        timestamp = datetime.strptime(bar.timestamp, _TIMESTAMP_FORMAT).replace(
            tzinfo=KST
        )
        if not window_start <= timestamp <= window_end:
            continue
        turnover = bar.amount if bar.amount is not None else bar.close * bar.volume
        point = ReactionMarketPoint(
            timestamp=timestamp,
            close=bar.close,
            turnover=turnover,
        )
        existing = points.get(timestamp)
        if existing is not None and existing != point:
            raise ValueError("conflicting duplicate Kiwoom reaction point")
        points[timestamp] = point
    return tuple(points[timestamp] for timestamp in sorted(points))


def _source_checksum(
    stock: tuple[ReactionMarketPoint, ...],
    benchmark: tuple[ReactionMarketPoint, ...],
    api_id: str,
) -> str:
    payload = {
        "api_id": api_id,
        "stock": _canonical_points(stock),
        "benchmark": _canonical_points(benchmark),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _canonical_points(points: tuple[ReactionMarketPoint, ...]) -> list[dict[str, str]]:
    return [
        {
            "timestamp": point.timestamp.isoformat(),
            "close": str(point.close),
            "turnover": str(point.turnover),
        }
        for point in points
    ]
