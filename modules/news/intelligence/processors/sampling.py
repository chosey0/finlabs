"""Deterministic event grouping, leakage-safe splits, and control sampling.

Two data-design defects motivate this module:

* News only entered the dataset because a (likely surging) candle was selected,
  so the sampling of which article appears is correlated with the very price
  reaction we want to predict. ``build_control_sampling_plan`` emits random,
  reproducible ``(security, anchor)`` points that are *not* conditioned on a
  move, so negatives can flow through the same discovery path.
* Articles inside the same short window share one underlying price move, so a
  random train/test split leaks that move across folds. ``assign_event_groups``
  clusters samples whose label windows can overlap into one event, and
  ``assign_split`` keeps every member of an event in the same fold.

Everything here is pure and deterministic: identical inputs (and seeds) always
produce identical groups, splits, and control points.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_EVENT_HORIZON_MINUTES = 30
DEFAULT_SPLIT_RATIOS: tuple[tuple[str, float], ...] = (
    ("train", 0.8),
    ("validation", 0.1),
    ("test", 0.1),
)


@dataclass(frozen=True, slots=True)
class EventMember:
    """One sample's identity for event grouping."""

    key: str
    security_id: str
    anchor: datetime


@dataclass(frozen=True, slots=True)
class ControlSamplePoint:
    """A random, move-independent anchor to drive negative news discovery."""

    security_id: str
    control_anchor: datetime


def assign_event_groups(
    members: Iterable[EventMember],
    *,
    horizon_minutes: int = DEFAULT_EVENT_HORIZON_MINUTES,
) -> dict[str, str]:
    """Group samples whose label windows can overlap into one event.

    Within a security the anchors are sorted and a new event begins whenever the
    gap to the previous anchor exceeds ``horizon_minutes`` -- the same horizon as
    the reaction label window, so any two members whose ``[t, t+horizon]`` windows
    can overlap land in the same event. The returned mapping is ``key -> event_id``
    and is independent of input order.
    """

    if horizon_minutes <= 0:
        raise ValueError("event horizon must be positive")
    horizon = timedelta(minutes=horizon_minutes)

    ordered = sorted(
        _validated_members(members),
        key=lambda member: (member.security_id, member.anchor, member.key),
    )

    groups: dict[str, str] = {}
    current_security: str | None = None
    previous_anchor: datetime | None = None
    event_id: str | None = None
    for member in ordered:
        starts_new_event = (
            member.security_id != current_security
            or previous_anchor is None
            or member.anchor - previous_anchor > horizon
        )
        if starts_new_event:
            current_security = member.security_id
            event_id = f"{member.security_id}|{member.anchor.isoformat()}"
        assert event_id is not None
        groups[member.key] = event_id
        previous_anchor = member.anchor
    return groups


def assign_split(
    event_id: str,
    *,
    salt: str,
    ratios: Sequence[tuple[str, float]] = DEFAULT_SPLIT_RATIOS,
) -> str:
    """Map an event to a fold deterministically by hashing ``salt + event_id``.

    Keying on ``event_id`` (not the sample) guarantees every member of an event
    receives the same fold, so a shared price move never straddles train/test.
    """

    normalized = _validated_ratios(ratios)
    digest = hashlib.sha256(f"{salt}\x00{event_id}".encode("utf-8")).digest()
    position = int.from_bytes(digest[:8], "big") / float(1 << 64)
    cumulative = 0.0
    for name, fraction in normalized:
        cumulative += fraction
        if position < cumulative:
            return name
    return normalized[-1][0]


def build_control_sampling_plan(
    *,
    securities: Sequence[str],
    sessions: Sequence[tuple[str, Sequence[datetime]]],
    seed: str,
    per_session: int = 1,
) -> tuple[ControlSamplePoint, ...]:
    """Draw reproducible random anchors not conditioned on any price move.

    ``sessions`` pairs a session id with that session's valid anchor minutes
    (timezone-aware, on the trading grid). For each session and security we draw
    ``per_session`` anchors with a seeded RNG, so the same ``seed`` always yields
    the same control set. Feed each point to ``discover_news`` tagged
    ``random_control`` to collect leakage-free negatives.
    """

    if per_session <= 0:
        raise ValueError("per_session must be positive")
    if not securities:
        raise ValueError("at least one security is required")

    rng = random.Random(_seed_int(seed))
    points: list[ControlSamplePoint] = []
    for _session_id, minutes in sessions:
        if not minutes:
            continue
        for minute in minutes:
            _require_aware(minute, "control session minute")
        for security_id in securities:
            for _ in range(per_session):
                anchor = minutes[rng.randrange(len(minutes))]
                points.append(
                    ControlSamplePoint(security_id=security_id, control_anchor=anchor)
                )
    return tuple(points)


def _validated_members(members: Iterable[EventMember]) -> list[EventMember]:
    validated: list[EventMember] = []
    for member in members:
        _require_aware(member.anchor, "event member anchor")
        validated.append(member)
    return validated


def _validated_ratios(
    ratios: Sequence[tuple[str, float]],
) -> tuple[tuple[str, float], ...]:
    if not ratios:
        raise ValueError("split ratios must be non-empty")
    names = [name for name, _ in ratios]
    if len(names) != len(set(names)):
        raise ValueError("split fold names must be unique")
    if any(fraction <= 0 for _, fraction in ratios):
        raise ValueError("split fractions must be positive")
    total = sum(fraction for _, fraction in ratios)
    if abs(total - 1.0) > 1e-9:
        raise ValueError("split fractions must sum to 1.0")
    return tuple((name, float(fraction)) for name, fraction in ratios)


def _seed_int(seed: str) -> int:
    return int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
