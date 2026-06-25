"""Deterministic immutable dataset snapshot canonicalization."""

from __future__ import annotations

import hashlib
import io
import json
import csv
import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from modules.news.intelligence.processors.sampling import (
    DEFAULT_EVENT_HORIZON_MINUTES,
    DEFAULT_SPLIT_RATIOS,
    EventMember,
    assign_event_groups,
    assign_split,
)


@dataclass(frozen=True, slots=True)
class DatasetSnapshot:
    dataset_id: str
    purpose: str
    cohort: str
    snapshot_checksum: str
    manifest: Mapping[str, Any]
    members: tuple[Mapping[str, Any], ...]
    exclusions: tuple[Mapping[str, Any], ...]


def build_dataset_snapshot(
    *,
    dataset_id: str,
    purpose: str,
    cohort: str,
    candidates: tuple[Mapping[str, Any], ...],
    split_salt: str | None = None,
    split_ratios: Sequence[tuple[str, float]] = DEFAULT_SPLIT_RATIOS,
    event_horizon_minutes: int = DEFAULT_EVENT_HORIZON_MINUTES,
    surge_threshold_std: Decimal = Decimal("2"),
) -> DatasetSnapshot:
    if purpose not in {"relevance_training", "reaction_training", "combined"}:
        raise ValueError("unsupported dataset purpose")
    if cohort not in {"live_first_seen", "historical_publication_proxy"}:
        raise ValueError("unsupported dataset cohort")
    salt = dataset_id if split_salt is None else split_salt
    included: list[dict[str, Any]] = []
    excluded: list[Mapping[str, Any]] = []
    for candidate in candidates:
        frozen = _canonical_member(candidate, cohort)
        reason = _exclusion_reason(purpose, frozen)
        if reason is None:
            included.append(frozen)
        else:
            excluded.append({"article_id": frozen["article_id"], "reason": reason})
    included.sort(
        key=lambda row: (
            row["effective_label_anchor"],
            row["article_id"],
            row["market"],
            row["symbol"],
        )
    )
    excluded.sort(key=lambda row: (row["article_id"], row["reason"]))

    # Cluster samples whose label windows can overlap into one event, then route
    # every member of an event to the same fold so a shared price move never
    # straddles train/test. event_id/split are derived (not stored on samples)
    # so they recompute identically and remain auditable in the manifest.
    event_ids = assign_event_groups(
        (
            EventMember(
                key=row["sample_id"],
                security_id=row["security_id"],
                anchor=datetime.fromisoformat(row["effective_label_anchor"]),
            )
            for row in included
        ),
        horizon_minutes=event_horizon_minutes,
    )
    split_counts: dict[str, int] = {}
    distinct_events: set[str] = set()
    for row in included:
        event_id = event_ids[row["sample_id"]]
        split = assign_split(event_id, salt=salt, ratios=split_ratios)
        row["event_id"] = event_id
        row["split"] = split
        distinct_events.add(event_id)
        split_counts[split] = split_counts.get(split, 0) + 1

    # Cross-sectional standardization (per trading day, across that day's names)
    # and the derived binary surge target. The per-stock time-series standardized
    # value is the primary label; this adds the contemporaneous cross-section so
    # ranking can compare names within a day. Same-time cross-section is not
    # leakage: it is available at inference when ranking the day's candidates.
    _assign_cross_sectional_std(included)
    surge_count = 0
    for row in included:
        surge = _surge_label(row["abnormal_return_std"], surge_threshold_std)
        row["surge_label"] = surge
        surge_count += surge

    manifest = {
        "schema_version": "news-intelligence-dataset-v4",
        "dataset_id": dataset_id,
        "purpose": purpose,
        "cohort": cohort,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "exclusion_counts": _counts(excluded),
        "event_count": len(distinct_events),
        "split_counts": dict(sorted(split_counts.items())),
        "origin_counts": _origin_counts(included),
        "surge_count": surge_count,
        "label_config": {
            "primary_target": "abnormal_return_std",
            "surge_threshold_std": str(surge_threshold_std),
        },
        "split_config": {
            "salt": salt,
            "event_horizon_minutes": event_horizon_minutes,
            "ratios": [list(item) for item in split_ratios],
        },
        "member_annotation_revision_ids": [row["annotation_id"] for row in included],
    }
    logical = {
        "manifest": manifest,
        "members": included,
        "exclusions": excluded,
    }
    checksum = hashlib.sha256(_json_bytes(logical)).hexdigest()
    return DatasetSnapshot(
        dataset_id=dataset_id,
        purpose=purpose,
        cohort=cohort,
        snapshot_checksum=checksum,
        manifest={**manifest, "snapshot_checksum": checksum},
        members=tuple(included),
        exclusions=tuple(excluded),
    )


def snapshot_json_bytes(snapshot: DatasetSnapshot) -> bytes:
    return (
        _json_bytes(
            {
                "manifest": snapshot.manifest,
                "members": snapshot.members,
                "exclusions": snapshot.exclusions,
            }
        )
        + b"\n"
    )


def snapshot_csv_bytes(snapshot: DatasetSnapshot) -> bytes:
    output = io.StringIO(newline="")
    fields = [
        "sample_id",
        "article_id",
        "security_id",
        "annotation_id",
        "final_value",
        "effective_label_anchor",
        "anchor_basis",
        "cohort",
        "market",
        "symbol",
        "title",
        "description",
        "reaction_class",
        "reaction_exclusion_reason",
        "beta",
        "abnormal_return",
        "abnormal_return_std",
        "abnormal_return_std_xs",
        "turnover_zscore",
        "surge_label",
        "sample_origin",
        "event_id",
        "split",
        "provenance_json",
        "annotation_json",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for member in snapshot.members:
        writer.writerow(
            {
                **{
                    field: member.get(field)
                    for field in fields
                    if field not in {"provenance_json", "annotation_json"}
                },
                "provenance_json": json.dumps(
                    member["provenance"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "annotation_json": json.dumps(
                    member["annotation"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
            }
        )
    return output.getvalue().encode("utf-8")


def _canonical_member(candidate: Mapping[str, Any], cohort: str) -> Mapping[str, Any]:
    required = {
        "sample_id",
        "article_id",
        "security_id",
        "annotation_id",
        "final_value",
        "effective_label_anchor",
        "anchor_basis",
        "cohort",
        "market",
        "symbol",
        "reaction_class",
        "reaction_exclusion_reason",
        "provenance",
        "annotation",
    }
    missing = sorted(required - candidate.keys())
    if missing:
        raise ValueError(f"dataset candidate missing fields: {', '.join(missing)}")
    if candidate["cohort"] != cohort:
        raise ValueError("cross-cohort dataset membership is forbidden")
    final_value = str(candidate["final_value"])
    if final_value not in {"relevant", "not_relevant", "uncertain"}:
        raise ValueError("unsupported final relevance value")
    expected_basis = {
        "live_first_seen": "first_seen_at",
        "historical_publication_proxy": "published_at_proxy",
    }[cohort]
    if candidate["anchor_basis"] != expected_basis:
        raise ValueError("anchor basis does not match dataset cohort")
    anchor = candidate["effective_label_anchor"]
    if (
        not isinstance(anchor, datetime)
        or anchor.tzinfo is None
        or anchor.utcoffset() is None
    ):
        raise ValueError("effective_label_anchor must be an aware datetime")
    return {
        "sample_id": str(candidate["sample_id"]),
        "article_id": str(candidate["article_id"]),
        "security_id": str(candidate["security_id"]),
        "annotation_id": str(candidate["annotation_id"]),
        "final_value": final_value,
        "effective_label_anchor": anchor.isoformat(),
        "anchor_basis": str(candidate["anchor_basis"]),
        "cohort": str(candidate["cohort"]),
        "market": str(candidate["market"]),
        "symbol": str(candidate["symbol"]),
        "title": str(candidate.get("title", "")),
        "description": str(candidate.get("description", "")),
        "reaction_class": candidate["reaction_class"],
        "reaction_exclusion_reason": candidate["reaction_exclusion_reason"],
        "sample_origin": _validated_origin(
            candidate.get("sample_origin", "event_selected")
        ),
        "beta": _decimal_str(candidate.get("beta")),
        "abnormal_return": _decimal_str(candidate.get("abnormal_return")),
        "abnormal_return_std": _decimal_str(candidate.get("abnormal_return_std")),
        "turnover_zscore": _decimal_str(candidate.get("turnover_zscore")),
        "provenance": json.loads(
            json.dumps(candidate["provenance"], ensure_ascii=False, sort_keys=True)
        ),
        "annotation": json.loads(
            json.dumps(candidate["annotation"], ensure_ascii=False, sort_keys=True)
        ),
    }


def _exclusion_reason(purpose: str, row: Mapping[str, Any]) -> str | None:
    value = row["final_value"]
    if purpose in {"relevance_training", "combined"} and value == "uncertain":
        return "uncertain_relevance"
    if purpose == "relevance_training":
        return None
    if purpose == "reaction_training":
        if value != "relevant":
            return "reaction_requires_relevant"
        if (
            row["reaction_exclusion_reason"] is not None
            or row["reaction_class"] is None
        ):
            return str(row["reaction_exclusion_reason"] or "reaction_label_missing")
        # The primary target is the standardized abnormal return; a sample without
        # it cannot serve the surge regression even if the categorical view exists.
        if row.get("abnormal_return_std") is None:
            return "reaction_std_unavailable"
    return None


def _counts(rows: list[Mapping[str, Any]]) -> Mapping[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        reason = str(row["reason"])
        result[reason] = result.get(reason, 0) + 1
    return dict(sorted(result.items()))


def _origin_counts(rows: list[Mapping[str, Any]]) -> Mapping[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        origin = str(row["sample_origin"])
        result[origin] = result.get(origin, 0) + 1
    return dict(sorted(result.items()))


def _assign_cross_sectional_std(rows: list[dict[str, Any]]) -> None:
    """Standardize the beta-adjusted abnormal return within each trading day.

    Mutates each row with ``abnormal_return_std_xs`` (a string or ``None``). Days
    with fewer than two valued members, or zero cross-sectional dispersion, leave
    the field ``None``.
    """

    by_day: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row["abnormal_return_std_xs"] = None
        if row["abnormal_return"] is None:
            continue
        day = datetime.fromisoformat(row["effective_label_anchor"]).date().isoformat()
        by_day.setdefault(day, []).append(row)

    for members in by_day.values():
        values = [Decimal(member["abnormal_return"]) for member in members]
        if len(values) < 2:
            continue
        mean = statistics.mean(values)
        deviation = statistics.pstdev(values)
        if deviation == 0:
            continue
        for member, value in zip(members, values):
            member["abnormal_return_std_xs"] = str((value - mean) / deviation)


def _surge_label(standardized: str | None, threshold: Decimal) -> int:
    if standardized is None:
        return 0
    return 1 if Decimal(standardized) >= threshold else 0


def _decimal_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _validated_origin(value: Any) -> str:
    origin = str(value)
    if origin not in {"event_selected", "random_control"}:
        raise ValueError("unsupported sample origin")
    return origin


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
