"""Point-in-time, fail-closed 30-trading-minute reaction labels."""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from modules.domain.news_intelligence import ReactionMarketPoint

LABEL_VERSION = "reaction-30trading-min-v1"


MarketPoint = ReactionMarketPoint


@dataclass(frozen=True, slots=True)
class ReactionPreview:
    effective_label_anchor: datetime
    feature_cutoff_at: datetime
    label_window_end: datetime | None
    stock_return: Decimal | None
    benchmark_return: Decimal | None
    abnormal_return: Decimal | None
    turnover_zscore: Decimal | None
    reaction_class: str | None
    is_strong_reaction: bool | None
    exclusion_reason: str | None
    label_version: str


def preview_reaction(
    *,
    effective_label_anchor: datetime,
    stock_points: tuple[MarketPoint, ...],
    benchmark_points: tuple[MarketPoint, ...] | None,
    session_minutes: tuple[datetime, ...] | None,
) -> ReactionPreview:
    _require_aware(effective_label_anchor)
    if session_minutes is None:
        return _excluded(effective_label_anchor, "session_calendar_unavailable")
    if benchmark_points is None:
        return _excluded(effective_label_anchor, "benchmark_unavailable")
    if effective_label_anchor not in session_minutes:
        return _excluded(effective_label_anchor, "anchor_outside_trading_session")
    try:
        _validate_timestamps(session_minutes, "session")
        _validate_points(stock_points, "stock")
        _validate_points(benchmark_points, "benchmark")
    except ValueError as error:
        return _excluded(effective_label_anchor, str(error))
    anchor_index = session_minutes.index(effective_label_anchor)
    if anchor_index + 30 >= len(session_minutes):
        return _excluded(effective_label_anchor, "incomplete_future_window")
    window_end = session_minutes[anchor_index + 30]
    required_window = session_minutes[anchor_index : anchor_index + 31]

    stock = {point.timestamp: point for point in stock_points}
    benchmark = {point.timestamp: point for point in benchmark_points}
    if any(timestamp not in stock for timestamp in required_window):
        return _excluded(effective_label_anchor, "incomplete_stock_window", window_end)
    if any(timestamp not in benchmark for timestamp in required_window):
        return _excluded(
            effective_label_anchor, "incomplete_benchmark_window", window_end
        )

    history = [
        point.turnover
        for point in sorted(stock_points, key=lambda item: item.timestamp)
        if point.timestamp <= effective_label_anchor
    ][-20:]
    if len(history) < 2:
        return _excluded(
            effective_label_anchor, "insufficient_turnover_history", window_end
        )
    deviation = statistics.pstdev(history)
    if deviation == 0:
        return _excluded(effective_label_anchor, "zero_turnover_variance", window_end)

    stock_return = stock[window_end].close / stock[effective_label_anchor].close - 1
    benchmark_return = (
        benchmark[window_end].close / benchmark[effective_label_anchor].close - 1
    )
    abnormal_return = stock_return - benchmark_return
    turnover_zscore = (
        stock[effective_label_anchor].turnover - statistics.mean(history)
    ) / deviation
    threshold = Decimal("0.02")
    reaction_class = (
        "positive"
        if abnormal_return >= threshold
        else "negative"
        if abnormal_return <= -threshold
        else "neutral"
    )
    return ReactionPreview(
        effective_label_anchor=effective_label_anchor,
        feature_cutoff_at=effective_label_anchor,
        label_window_end=window_end,
        stock_return=stock_return,
        benchmark_return=benchmark_return,
        abnormal_return=abnormal_return,
        turnover_zscore=turnover_zscore,
        reaction_class=reaction_class,
        is_strong_reaction=abs(abnormal_return) >= threshold and turnover_zscore >= 2,
        exclusion_reason=None,
        label_version=LABEL_VERSION,
    )


def _excluded(
    anchor: datetime,
    reason: str,
    window_end: datetime | None = None,
) -> ReactionPreview:
    return ReactionPreview(
        effective_label_anchor=anchor,
        feature_cutoff_at=anchor,
        label_window_end=window_end,
        stock_return=None,
        benchmark_return=None,
        abnormal_return=None,
        turnover_zscore=None,
        reaction_class=None,
        is_strong_reaction=None,
        exclusion_reason=reason,
        label_version=LABEL_VERSION,
    )


def _require_aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("effective_label_anchor must be timezone-aware")


def _validate_timestamps(values: tuple[datetime, ...], source: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(f"duplicate_{source}_timestamps")
    if tuple(sorted(values)) != values:
        raise ValueError(f"unordered_{source}_timestamps")
    for value in values:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"naive_{source}_timestamp")


def _validate_points(values: tuple[MarketPoint, ...], source: str) -> None:
    _validate_timestamps(tuple(point.timestamp for point in values), source)
