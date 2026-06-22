"""Deterministic immutable dataset snapshot canonicalization."""

from __future__ import annotations

import hashlib
import io
import json
import csv
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping


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
) -> DatasetSnapshot:
    if purpose not in {"relevance_training", "reaction_training", "combined"}:
        raise ValueError("unsupported dataset purpose")
    if cohort not in {"live_first_seen", "historical_publication_proxy"}:
        raise ValueError("unsupported dataset cohort")
    included: list[Mapping[str, Any]] = []
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
    manifest = {
        "schema_version": "news-intelligence-dataset-v1",
        "dataset_id": dataset_id,
        "purpose": purpose,
        "cohort": cohort,
        "included_count": len(included),
        "excluded_count": len(excluded),
        "exclusion_counts": _counts(excluded),
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
        "reaction_class",
        "reaction_exclusion_reason",
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
        "reaction_class": candidate["reaction_class"],
        "reaction_exclusion_reason": candidate["reaction_exclusion_reason"],
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
    return None


def _counts(rows: list[Mapping[str, Any]]) -> Mapping[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        reason = str(row["reason"])
        result[reason] = result.get(reason, 0) + 1
    return dict(sorted(result.items()))


def _json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
