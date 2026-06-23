"""Load surge-ranking samples from a frozen dataset snapshot and split them.

A snapshot member already carries the leakage-safe event id and IID split, the
continuous primary target, the binary surge label, and the point-in-time numeric
features. This module turns those members into typed rows and produces both the
IID (event-hash) split and a forward-in-time out-of-time holdout cut on event
boundaries, so the model can be judged the way it will be used live.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class SurgeSample:
    sample_id: str
    security_id: str
    market: str
    anchor: datetime
    event_id: str
    split: str
    sample_origin: str
    anchor_adjustment: str
    text: str
    # Point-in-time features (known at the feature cutoff):
    beta: float | None
    turnover_zscore: float | None
    # Targets:
    abnormal_return_std: float | None  # primary regression target
    surge_label: int  # auxiliary binary target

    @property
    def has_regression_target(self) -> bool:
        return self.abnormal_return_std is not None


@dataclass(frozen=True, slots=True)
class DataSplits:
    train: tuple[SurgeSample, ...]
    validation: tuple[SurgeSample, ...]
    iid_test: tuple[SurgeSample, ...]
    out_of_time_test: tuple[SurgeSample, ...]


def load_surge_samples(snapshot: Mapping[str, Any]) -> tuple[SurgeSample, ...]:
    """Parse a snapshot mapping (``{"manifest", "members", ...}``) into rows."""

    members = snapshot.get("members", ())
    return tuple(_to_sample(member) for member in members)


def partition(
    rows: Iterable[SurgeSample],
    *,
    out_of_time_fraction: float = 0.2,
) -> DataSplits:
    """Carve a forward-in-time holdout on event boundaries, then the IID split.

    The latest ``out_of_time_fraction`` of *events* (ordered by their newest
    anchor) becomes the out-of-time test, so no event straddles the temporal cut.
    Remaining events keep their stored event-hash split (train / validation /
    test), giving both an IID and a forward-time evaluation.
    """

    if not 0.0 <= out_of_time_fraction < 1.0:
        raise ValueError("out_of_time_fraction must be in [0, 1)")
    ordered_rows = sorted(rows, key=lambda row: (row.anchor, row.sample_id))
    if not ordered_rows:
        return DataSplits((), (), (), ())

    latest_event_anchor: dict[str, datetime] = {}
    for row in ordered_rows:
        current = latest_event_anchor.get(row.event_id)
        if current is None or row.anchor > current:
            latest_event_anchor[row.event_id] = row.anchor
    events_by_recency = sorted(
        latest_event_anchor, key=lambda event: (latest_event_anchor[event], event)
    )
    oot_count = int(len(events_by_recency) * out_of_time_fraction)
    out_of_time_events = set(events_by_recency[len(events_by_recency) - oot_count :])

    train: list[SurgeSample] = []
    validation: list[SurgeSample] = []
    iid_test: list[SurgeSample] = []
    out_of_time: list[SurgeSample] = []
    for row in ordered_rows:
        if row.event_id in out_of_time_events:
            out_of_time.append(row)
        elif row.split == "validation":
            validation.append(row)
        elif row.split == "test":
            iid_test.append(row)
        else:
            train.append(row)
    return DataSplits(
        train=tuple(train),
        validation=tuple(validation),
        iid_test=tuple(iid_test),
        out_of_time_test=tuple(out_of_time),
    )


def _to_sample(member: Mapping[str, Any]) -> SurgeSample:
    reaction = {}
    provenance = member.get("provenance")
    if isinstance(provenance, Mapping):
        nested = provenance.get("reaction")
        if isinstance(nested, Mapping):
            reaction = nested
    text = " ".join(
        part
        for part in (member.get("title", ""), member.get("description", ""))
        if part
    )
    return SurgeSample(
        sample_id=str(member["sample_id"]),
        security_id=str(member["security_id"]),
        market=str(member["market"]),
        anchor=datetime.fromisoformat(member["effective_label_anchor"]),
        event_id=str(member.get("event_id", member["sample_id"])),
        split=str(member.get("split", "train")),
        sample_origin=str(member.get("sample_origin", "event_selected")),
        anchor_adjustment=str(reaction.get("anchor_adjustment", "none")),
        text=text,
        beta=_to_float(member.get("beta")),
        turnover_zscore=_to_float(member.get("turnover_zscore")),
        abnormal_return_std=_to_float(member.get("abnormal_return_std")),
        surge_label=int(member.get("surge_label", 0) or 0),
    )


def _to_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)
