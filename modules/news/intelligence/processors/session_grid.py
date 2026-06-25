"""KRX regular-session minute grid and information-arrival anchor resolution.

Two reaction-label defects motivate this module:

* News that arrives after the close, before the open, or on a non-trading day
  used to be silently dropped, even though after-close disclosures are the most
  material. The market can only react at the *next* session open, so we roll the
  reaction anchor forward to the first tradable minute instead of excluding it.
* The publication timestamp is not the information-arrival instant and may not
  precede the price move. Keeping the *feature cutoff* (information time) separate
  from the *label window start* (first tradable minute) makes the alignment
  explicit: features are known at the cutoff, the label is measured from when the
  market could first act.

Everything here is pure. The KRX regular session is the continuous 09:00–15:30
KST window (no lunch break since 2000); trading days are supplied by the caller
(Kiwoom only returns bars on trading days, so holidays drop out for free).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from modules.domain.news_intelligence import KST

REGULAR_OPEN = time(9, 0)
REGULAR_CLOSE = time(15, 30)
# Inclusive 09:00..15:30 -> 391 one-minute marks.
REGULAR_SESSION_MINUTES = (
    (REGULAR_CLOSE.hour * 60 + REGULAR_CLOSE.minute)
    - (REGULAR_OPEN.hour * 60 + REGULAR_OPEN.minute)
    + 1
)

AnchorAdjustment = str  # "none" | "rolled_to_next_session" | "after_available_sessions"


@dataclass(frozen=True, slots=True)
class AnchorResolution:
    """How an information-arrival instant maps onto the trading grid."""

    feature_cutoff_at: datetime
    reaction_anchor: datetime | None
    adjustment: AnchorAdjustment


def regular_session_minutes(trading_dates: Iterable[date]) -> tuple[datetime, ...]:
    """Return the sorted KST minute grid for the given KRX trading dates.

    Each date contributes the inclusive 09:00..15:30 regular session. Holidays
    are excluded simply by not appearing in ``trading_dates``.
    """

    minutes: list[datetime] = []
    for trading_date in sorted(set(trading_dates)):
        open_at = datetime.combine(trading_date, REGULAR_OPEN, tzinfo=KST)
        minutes.extend(
            open_at + timedelta(minutes=index)
            for index in range(REGULAR_SESSION_MINUTES)
        )
    return tuple(minutes)


def weekday_trading_sessions(
    start: date, end: date
) -> tuple[tuple[str, tuple[datetime, ...]], ...]:
    """Regular-session minute grids for each weekday in ``[start, end]``.

    A control-sampling calendar for ``build_control_sampling_plan``: weekends are
    skipped, holidays are left in (a control anchor on a holiday simply yields no
    Kiwoom data downstream and is dropped), so no holiday source is required here.
    """

    if end < start:
        raise ValueError("end must not precede start")
    sessions: list[tuple[str, tuple[datetime, ...]]] = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # Monday..Friday
            sessions.append((current.isoformat(), regular_session_minutes([current])))
        current += timedelta(days=1)
    return tuple(sessions)


def resolve_reaction_anchor(
    *,
    anchor: datetime,
    session_minutes: tuple[datetime, ...],
) -> AnchorResolution:
    """Map an information-arrival instant to the first tradable minute >= it.

    * An anchor that lands on a trading minute is kept as-is (``none``).
    * An anchor outside a session rolls forward to the next session open
      (``rolled_to_next_session``); the publication time stays the feature cutoff.
    * An anchor past every supplied minute cannot be labelled
      (``after_available_sessions``).
    """

    if anchor.tzinfo is None or anchor.utcoffset() is None:
        raise ValueError("anchor must be timezone-aware")

    forward = [minute for minute in session_minutes if minute >= anchor]
    if not forward:
        return AnchorResolution(
            feature_cutoff_at=anchor,
            reaction_anchor=None,
            adjustment="after_available_sessions",
        )
    reaction_anchor = min(forward)
    adjustment = "none" if reaction_anchor == anchor else "rolled_to_next_session"
    return AnchorResolution(
        feature_cutoff_at=anchor,
        reaction_anchor=reaction_anchor,
        adjustment=adjustment,
    )
