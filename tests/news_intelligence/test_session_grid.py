from __future__ import annotations

from datetime import date, datetime

import pytest

from modules.domain.news_intelligence import KST
from modules.news.intelligence.processors.session_grid import (
    regular_session_minutes,
    resolve_reaction_anchor,
)


def test_regular_session_minutes_span_open_to_close_inclusive() -> None:
    minutes = regular_session_minutes([date(2026, 6, 17)])

    assert len(minutes) == 391  # 09:00..15:30 inclusive
    assert minutes[0] == datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    assert minutes[-1] == datetime(2026, 6, 17, 15, 30, tzinfo=KST)
    assert all(minute.tzinfo is not None for minute in minutes)


def test_regular_session_minutes_concatenate_sorted_unique_dates() -> None:
    minutes = regular_session_minutes([date(2026, 6, 18), date(2026, 6, 17), date(2026, 6, 17)])

    assert len(minutes) == 391 * 2  # deduplicated, two sessions
    assert minutes[390] == datetime(2026, 6, 17, 15, 30, tzinfo=KST)
    assert minutes[391] == datetime(2026, 6, 18, 9, 0, tzinfo=KST)  # crosses the gap


def test_resolve_keeps_in_session_anchor() -> None:
    grid = regular_session_minutes([date(2026, 6, 17)])
    anchor = datetime(2026, 6, 17, 9, 30, tzinfo=KST)

    resolution = resolve_reaction_anchor(anchor=anchor, session_minutes=grid)

    assert resolution.adjustment == "none"
    assert resolution.reaction_anchor == anchor
    assert resolution.feature_cutoff_at == anchor


def test_resolve_rolls_pre_open_and_after_close_to_next_session_open() -> None:
    grid = regular_session_minutes([date(2026, 6, 17), date(2026, 6, 18)])

    pre_open = resolve_reaction_anchor(
        anchor=datetime(2026, 6, 17, 8, 30, tzinfo=KST), session_minutes=grid
    )
    after_close = resolve_reaction_anchor(
        anchor=datetime(2026, 6, 17, 16, 0, tzinfo=KST), session_minutes=grid
    )

    assert pre_open.adjustment == "rolled_to_next_session"
    assert pre_open.reaction_anchor == datetime(2026, 6, 17, 9, 0, tzinfo=KST)
    assert after_close.adjustment == "rolled_to_next_session"
    assert after_close.reaction_anchor == datetime(2026, 6, 18, 9, 0, tzinfo=KST)
    # The publication time stays the feature cutoff even after rolling forward.
    assert after_close.feature_cutoff_at == datetime(2026, 6, 17, 16, 0, tzinfo=KST)


def test_resolve_reports_anchor_past_all_sessions() -> None:
    grid = regular_session_minutes([date(2026, 6, 17)])

    resolution = resolve_reaction_anchor(
        anchor=datetime(2026, 6, 17, 16, 0, tzinfo=KST), session_minutes=grid
    )

    assert resolution.reaction_anchor is None
    assert resolution.adjustment == "after_available_sessions"


def test_resolve_rejects_naive_anchor() -> None:
    grid = regular_session_minutes([date(2026, 6, 17)])
    with pytest.raises(ValueError, match="timezone-aware"):
        resolve_reaction_anchor(anchor=datetime(2026, 6, 17, 9, 30), session_minutes=grid)
