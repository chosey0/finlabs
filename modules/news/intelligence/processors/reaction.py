"""Point-in-time, fail-closed 30-trading-minute reaction labels.

Version 3 makes the continuous reaction magnitude the canonical label and fixes
the two signal defects behind it:

* Beta correction. The abnormal return is ``stock_return - beta * benchmark_return``
  with ``beta`` estimated from pre-anchor one-minute abnormal returns (point in
  time, clamped, falling back to 1), so a high-beta name's mechanical co-movement
  with the market is no longer mistaken for a news reaction.
* Time-series standardisation. ``abnormal_return_std`` divides the abnormal return
  by the stock's own 30-minute abnormal-return volatility (pre-anchor one-minute
  abnormal-return stdev scaled by sqrt(30)), so a fixed +/-2% no longer means
  different things for a calm large cap and a jumpy small cap. This standardized
  value is the primary regression target; ``reaction_class`` is now an auxiliary
  categorical view.

Anchor handling (roll-forward off-session anchors, feature-cutoff vs window-start
separation, pre-anchor drift flag) is unchanged from v2.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal

from modules.domain.news_intelligence import ReactionMarketPoint
from modules.news.intelligence.processors.session_grid import resolve_reaction_anchor

LABEL_VERSION = "reaction-30trading-min-v3"
PRE_ANCHOR_LOOKBACK_MINUTES = 5
MIN_BETA_OBSERVATIONS = 10
BETA_MIN = Decimal("0")
BETA_MAX = Decimal("3")
HORIZON_MINUTES = 30
_SQRT_HORIZON = Decimal(HORIZON_MINUTES).sqrt()


MarketPoint = ReactionMarketPoint


@dataclass(frozen=True, slots=True)
class ReactionPreview:
    effective_label_anchor: datetime
    feature_cutoff_at: datetime
    label_window_start: datetime | None
    label_window_end: datetime | None
    anchor_adjustment: str
    beta: Decimal | None
    stock_return: Decimal | None
    benchmark_return: Decimal | None
    abnormal_return: Decimal | None
    abnormal_return_std: Decimal | None
    turnover_zscore: Decimal | None
    pre_anchor_abnormal_return: Decimal | None
    pre_anchor_drift: bool | None
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
    try:
        _validate_timestamps(session_minutes, "session")
        _validate_points(stock_points, "stock")
        _validate_points(benchmark_points, "benchmark")
    except ValueError as error:
        return _excluded(effective_label_anchor, str(error))

    resolution = resolve_reaction_anchor(
        anchor=effective_label_anchor, session_minutes=session_minutes
    )
    reaction_anchor = resolution.reaction_anchor
    if reaction_anchor is None:
        return _excluded(
            effective_label_anchor,
            "anchor_after_available_sessions",
            adjustment=resolution.adjustment,
        )

    threshold = Decimal("0.02")
    anchor_index = session_minutes.index(reaction_anchor)
    if anchor_index + 30 >= len(session_minutes):
        return _excluded(
            effective_label_anchor,
            "incomplete_future_window",
            adjustment=resolution.adjustment,
            label_window_start=reaction_anchor,
        )
    window_end = session_minutes[anchor_index + 30]
    required_window = session_minutes[anchor_index : anchor_index + 31]

    stock = {point.timestamp: point for point in stock_points}
    benchmark = {point.timestamp: point for point in benchmark_points}
    if any(timestamp not in stock for timestamp in required_window):
        return _excluded(
            effective_label_anchor,
            "incomplete_stock_window",
            window_end,
            adjustment=resolution.adjustment,
            label_window_start=reaction_anchor,
        )
    if any(timestamp not in benchmark for timestamp in required_window):
        return _excluded(
            effective_label_anchor,
            "incomplete_benchmark_window",
            window_end,
            adjustment=resolution.adjustment,
            label_window_start=reaction_anchor,
        )

    history = [
        point.turnover
        for point in sorted(stock_points, key=lambda item: item.timestamp)
        if point.timestamp <= reaction_anchor
    ][-20:]
    if len(history) < 2:
        return _excluded(
            effective_label_anchor,
            "insufficient_turnover_history",
            window_end,
            adjustment=resolution.adjustment,
            label_window_start=reaction_anchor,
        )
    deviation = statistics.pstdev(history)
    if deviation == 0:
        return _excluded(
            effective_label_anchor,
            "zero_turnover_variance",
            window_end,
            adjustment=resolution.adjustment,
            label_window_start=reaction_anchor,
        )

    pre_anchor_abnormal = _pre_anchor_minute_abnormals(stock, benchmark, reaction_anchor)
    beta = _estimate_beta(pre_anchor_abnormal)
    stock_return = stock[window_end].close / stock[reaction_anchor].close - 1
    benchmark_return = (
        benchmark[window_end].close / benchmark[reaction_anchor].close - 1
    )
    abnormal_return = stock_return - beta * benchmark_return
    abnormal_return_std = _time_series_standardized(
        abnormal_return=abnormal_return,
        pre_anchor_abnormal=pre_anchor_abnormal,
        beta=beta,
    )
    turnover_zscore = (
        stock[reaction_anchor].turnover - statistics.mean(history)
    ) / deviation
    reaction_class = (
        "positive"
        if abnormal_return >= threshold
        else "negative"
        if abnormal_return <= -threshold
        else "neutral"
    )
    pre_drift_value, pre_drift_flag = _pre_anchor_drift(
        stock=stock,
        benchmark=benchmark,
        session_minutes=session_minutes,
        anchor_index=anchor_index,
        adjustment=resolution.adjustment,
        threshold=threshold,
    )
    return ReactionPreview(
        effective_label_anchor=effective_label_anchor,
        feature_cutoff_at=effective_label_anchor,
        label_window_start=reaction_anchor,
        label_window_end=window_end,
        anchor_adjustment=resolution.adjustment,
        beta=beta,
        stock_return=stock_return,
        benchmark_return=benchmark_return,
        abnormal_return=abnormal_return,
        abnormal_return_std=abnormal_return_std,
        turnover_zscore=turnover_zscore,
        pre_anchor_abnormal_return=pre_drift_value,
        pre_anchor_drift=pre_drift_flag,
        reaction_class=reaction_class,
        is_strong_reaction=abs(abnormal_return) >= threshold and turnover_zscore >= 2,
        exclusion_reason=None,
        label_version=LABEL_VERSION,
    )


def _pre_anchor_minute_abnormals(
    stock: dict[datetime, MarketPoint],
    benchmark: dict[datetime, MarketPoint],
    reaction_anchor: datetime,
) -> list[tuple[Decimal, Decimal]]:
    """Consecutive pre-anchor one-minute (stock, benchmark) simple returns.

    Only minutes whose previous minute exists in both series are kept, and only up
    to and including the reaction anchor, so every observation is point in time.
    """

    pairs: list[tuple[Decimal, Decimal]] = []
    for timestamp in sorted(stock):
        if timestamp > reaction_anchor:
            break
        previous = timestamp - timedelta(minutes=1)
        if previous not in stock or timestamp not in benchmark or previous not in benchmark:
            continue
        stock_return = stock[timestamp].close / stock[previous].close - 1
        benchmark_return = benchmark[timestamp].close / benchmark[previous].close - 1
        pairs.append((stock_return, benchmark_return))
    return pairs


def _estimate_beta(pairs: list[tuple[Decimal, Decimal]]) -> Decimal:
    """OLS slope of stock on benchmark one-minute returns, clamped to [0, 3].

    Falls back to 1 when there are too few observations or the benchmark has no
    variance, so an unidentifiable beta degrades to the market-adjusted return.
    """

    if len(pairs) < MIN_BETA_OBSERVATIONS:
        return Decimal("1")
    mean_stock = statistics.mean(stock for stock, _ in pairs)
    mean_benchmark = statistics.mean(benchmark for _, benchmark in pairs)
    covariance = sum(
        (stock - mean_stock) * (benchmark - mean_benchmark)
        for stock, benchmark in pairs
    )
    variance = sum((benchmark - mean_benchmark) ** 2 for _, benchmark in pairs)
    if variance == 0:
        return Decimal("1")
    beta = covariance / variance
    return min(BETA_MAX, max(BETA_MIN, beta))


def _time_series_standardized(
    *,
    abnormal_return: Decimal,
    pre_anchor_abnormal: list[tuple[Decimal, Decimal]],
    beta: Decimal,
) -> Decimal | None:
    """Abnormal return in units of the stock's own 30-minute abnormal volatility.

    The denominator is the pre-anchor one-minute abnormal-return stdev scaled by
    sqrt(30); ``None`` when there is too little history or zero volatility (the
    sample then carries the raw abnormal return but no standardized label).
    """

    series = [stock - beta * benchmark for stock, benchmark in pre_anchor_abnormal]
    if len(series) < 2:
        return None
    sigma_one_minute = statistics.pstdev(series)
    if sigma_one_minute == 0:
        return None
    return abnormal_return / (sigma_one_minute * _SQRT_HORIZON)


def _pre_anchor_drift(
    *,
    stock: dict[datetime, MarketPoint],
    benchmark: dict[datetime, MarketPoint],
    session_minutes: tuple[datetime, ...],
    anchor_index: int,
    adjustment: str,
    threshold: Decimal,
) -> tuple[Decimal | None, bool | None]:
    """Flag in-session anchors whose price already moved before the timestamp.

    A large abnormal move in the minutes just before the anchor suggests the
    publication time lags the real event (lookahead risk). Only meaningful for
    anchors taken as-is: a rolled-forward anchor's "pre" minutes are the legitimate
    overnight gap, not contamination.
    """

    if adjustment != "none":
        return None, None
    pre_index = anchor_index - PRE_ANCHOR_LOOKBACK_MINUTES
    if pre_index < 0:
        return None, None
    reaction_anchor = session_minutes[anchor_index]
    pre_anchor = session_minutes[pre_index]
    if any(
        moment not in series
        for series in (stock, benchmark)
        for moment in (pre_anchor, reaction_anchor)
    ):
        return None, None
    stock_drift = stock[reaction_anchor].close / stock[pre_anchor].close - 1
    benchmark_drift = benchmark[reaction_anchor].close / benchmark[pre_anchor].close - 1
    abnormal = stock_drift - benchmark_drift
    return abnormal, abs(abnormal) >= threshold


def _excluded(
    anchor: datetime,
    reason: str,
    window_end: datetime | None = None,
    *,
    adjustment: str = "none",
    label_window_start: datetime | None = None,
) -> ReactionPreview:
    return ReactionPreview(
        effective_label_anchor=anchor,
        feature_cutoff_at=anchor,
        label_window_start=label_window_start,
        label_window_end=window_end,
        anchor_adjustment=adjustment,
        beta=None,
        stock_return=None,
        benchmark_return=None,
        abnormal_return=None,
        abnormal_return_std=None,
        turnover_zscore=None,
        pre_anchor_abnormal_return=None,
        pre_anchor_drift=None,
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
