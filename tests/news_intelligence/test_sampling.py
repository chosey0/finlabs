from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from modules.domain.news_intelligence import KST
from modules.news.intelligence.processors.sampling import (
    ControlSamplePoint,
    EventMember,
    assign_event_groups,
    assign_split,
    build_control_sampling_plan,
)


def _member(key: str, security_id: str, anchor: datetime) -> EventMember:
    return EventMember(key=key, security_id=security_id, anchor=anchor)


def test_event_groups_cluster_within_horizon_and_split_beyond() -> None:
    base = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    members = [
        _member("a", "KOSPI:005930", base),
        _member("b", "KOSPI:005930", base + timedelta(minutes=25)),  # gap 25 <= 30
        _member("c", "KOSPI:005930", base + timedelta(minutes=70)),  # gap 45 > 30
        _member("d", "KOSDAQ:123456", base + timedelta(minutes=10)),  # other security
    ]

    groups = assign_event_groups(members, horizon_minutes=30)

    # a and b share a price-move window -> one event; c is a separate event.
    assert groups["a"] == groups["b"]
    assert groups["a"] != groups["c"]
    # A different security never merges, even with a nearby anchor.
    assert groups["d"] not in {groups["a"], groups["c"]}


def test_event_groups_are_order_independent() -> None:
    base = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    members = [
        _member("a", "KOSPI:005930", base),
        _member("b", "KOSPI:005930", base + timedelta(minutes=20)),
        _member("c", "KOSPI:005930", base + timedelta(minutes=90)),
    ]

    forward = assign_event_groups(members, horizon_minutes=30)
    reverse = assign_event_groups(list(reversed(members)), horizon_minutes=30)

    assert forward == reverse


def test_event_groups_reject_naive_anchor_and_bad_horizon() -> None:
    aware = datetime(2026, 6, 17, 9, 30, tzinfo=KST)
    with pytest.raises(ValueError, match="positive"):
        assign_event_groups([_member("a", "s", aware)], horizon_minutes=0)
    with pytest.raises(ValueError, match="timezone-aware"):
        assign_event_groups([_member("a", "s", datetime(2026, 6, 17, 9, 30))])


def test_split_is_deterministic_and_within_ratio_names() -> None:
    salt = "dataset-1"
    names = {"train", "validation", "test"}
    events = [f"KOSPI:005930|2026-06-17T{hour:02d}:30:00+09:00" for hour in range(9, 16)]

    first = {event: assign_split(event, salt=salt) for event in events}
    second = {event: assign_split(event, salt=salt) for event in events}

    assert first == second  # reproducible
    assert set(first.values()) <= names
    # A different salt is free to reassign folds (proves salt actually applies).
    other = {event: assign_split(event, salt="other") for event in events}
    assert other != first or len(events) == 1


def test_split_rejects_malformed_ratios() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        assign_split("e", salt="s", ratios=(("train", 0.5), ("test", 0.4)))
    with pytest.raises(ValueError, match="unique"):
        assign_split("e", salt="s", ratios=(("train", 0.5), ("train", 0.5)))
    with pytest.raises(ValueError, match="positive"):
        assign_split("e", salt="s", ratios=(("train", 1.5), ("test", -0.5)))


def test_control_plan_is_seeded_reproducible_and_draws_from_minutes() -> None:
    minutes = tuple(
        datetime(2026, 6, 17, 9, 30, tzinfo=KST) + timedelta(minutes=index)
        for index in range(60)
    )
    sessions = (("2026-06-17", minutes),)
    securities = ("KOSPI:005930", "KOSDAQ:123456")

    plan = build_control_sampling_plan(
        securities=securities, sessions=sessions, seed="seed-1", per_session=2
    )
    replay = build_control_sampling_plan(
        securities=securities, sessions=sessions, seed="seed-1", per_session=2
    )

    assert plan == replay  # deterministic for a fixed seed
    assert len(plan) == len(securities) * 2  # per_session draws per security
    assert all(isinstance(point, ControlSamplePoint) for point in plan)
    assert all(point.control_anchor in minutes for point in plan)
    assert {point.security_id for point in plan} == set(securities)

    different = build_control_sampling_plan(
        securities=securities, sessions=sessions, seed="seed-2", per_session=2
    )
    assert different != plan  # a different seed yields a different draw


def test_control_plan_validates_inputs() -> None:
    minutes = (datetime(2026, 6, 17, 9, 30, tzinfo=KST),)
    with pytest.raises(ValueError, match="per_session"):
        build_control_sampling_plan(
            securities=("s",), sessions=(("d", minutes),), seed="x", per_session=0
        )
    with pytest.raises(ValueError, match="at least one security"):
        build_control_sampling_plan(securities=(), sessions=(("d", minutes),), seed="x")
    with pytest.raises(ValueError, match="timezone-aware"):
        build_control_sampling_plan(
            securities=("s",),
            sessions=(("d", (datetime(2026, 6, 17, 9, 30),)),),
            seed="x",
        )
