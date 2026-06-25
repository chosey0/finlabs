"""Storage-only repositories and persistent idempotency state machine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Any

import psycopg


class ClaimDisposition(StrEnum):
    ACQUIRED = "acquired"
    REPLAY = "replay"
    IN_PROGRESS = "in_progress"


class IdempotencyConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ClaimResult:
    disposition: ClaimDisposition
    result_ref: str | None = None


@dataclass(frozen=True, slots=True)
class AnnotationRevisionRecord:
    annotation_id: str
    sample_id: str
    article_id: str
    security_id: str
    revision: int
    previous_annotation_id: str | None
    final_value: str
    suggestion_value: str
    evidence_json: str
    rule_version: str
    actor: str
    note: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class SampleRecord:
    sample_id: str
    article_id: str
    security_id: str
    market: str
    symbol: str
    title: str
    description: str
    published_at: datetime
    effective_label_anchor: datetime
    anchor_basis: str
    cohort: str
    provenance_json: str
    reaction_class: str | None
    reaction_exclusion_reason: str | None
    sample_origin: str = "event_selected"
    beta: Decimal | None = None
    abnormal_return: Decimal | None = None
    abnormal_return_std: Decimal | None = None
    turnover_zscore: Decimal | None = None


@dataclass(frozen=True, slots=True)
class ExportRecord:
    export_id: str
    dataset_id: str
    sink: str
    state: str
    expected_path: str
    expected_checksum: str
    artifact_checksum: str | None
    error_code: str | None


def canonical_request_hash(payload: Any) -> str:
    rendered = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def claim_operation(
    connection: psycopg.Connection,
    *,
    operation: str,
    idempotency_key: str,
    request_hash: str,
    owner_id: str,
    now: datetime,
    lease_duration: timedelta,
    manage_transaction: bool = True,
) -> ClaimResult:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    if lease_duration <= timedelta(0):
        raise ValueError("lease_duration must be positive")

    try:
        row = connection.execute(
            """
            SELECT request_hash, state, owner_id,
                   lease_expires_at, result_ref
            FROM intelligence_idempotency
            WHERE operation = %s AND idempotency_key = %s
            """,
            [operation, idempotency_key],
        ).fetchone()
        lease_expires_at = now + lease_duration
        if row is None:
            connection.execute(
                """
                INSERT INTO intelligence_idempotency (
                    operation, idempotency_key, request_hash, state, owner_id,
                    lease_expires_at, created_at, updated_at
                ) VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s)
                """,
                [
                    operation,
                    idempotency_key,
                    request_hash,
                    owner_id,
                    lease_expires_at,
                    now,
                    now,
                ],
            )
            result = ClaimResult(ClaimDisposition.ACQUIRED)
        else:
            stored_hash, state, stored_owner, stored_expiry, result_ref = row
            if stored_hash != request_hash:
                raise IdempotencyConflictError("idempotency key request hash conflict")
            if state == "succeeded":
                result = ClaimResult(ClaimDisposition.REPLAY, result_ref)
            elif (
                state == "pending" and stored_expiry is not None and stored_expiry > now
            ):
                result = ClaimResult(ClaimDisposition.IN_PROGRESS)
            else:
                updated = connection.execute(
                    """
                    UPDATE intelligence_idempotency
                    SET state = 'pending', owner_id = %s, lease_expires_at = %s,
                        error_code = NULL, updated_at = %s
                    WHERE operation = %s AND idempotency_key = %s
                      AND request_hash = %s
                      AND (state = 'rolled_back' OR lease_expires_at <= %s)
                    RETURNING owner_id
                    """,
                    [
                        owner_id,
                        lease_expires_at,
                        now,
                        operation,
                        idempotency_key,
                        request_hash,
                        now,
                    ],
                ).fetchone()
                result = ClaimResult(
                    ClaimDisposition.ACQUIRED
                    if updated and updated[0] == owner_id
                    else ClaimDisposition.IN_PROGRESS
                )
        if manage_transaction:
            connection.commit()
        return result
    except Exception:
        if manage_transaction:
            connection.rollback()
        raise


def mark_operation_succeeded(
    connection: psycopg.Connection,
    *,
    operation: str,
    idempotency_key: str,
    owner_id: str,
    result_ref: str,
    now: datetime,
) -> None:
    row = connection.execute(
        """
        UPDATE intelligence_idempotency
        SET state = 'succeeded', result_ref = %s, owner_id = NULL,
            lease_expires_at = NULL, updated_at = %s
        WHERE operation = %s AND idempotency_key = %s
          AND state = 'pending' AND owner_id = %s
        RETURNING result_ref
        """,
        [result_ref, now, operation, idempotency_key, owner_id],
    ).fetchone()
    if row is None:
        raise IdempotencyConflictError("idempotency claim is not owned")


def mark_operation_rolled_back(
    connection: psycopg.Connection,
    *,
    operation: str,
    idempotency_key: str,
    owner_id: str,
    error_code: str,
    now: datetime,
) -> None:
    row = connection.execute(
        """
        UPDATE intelligence_idempotency
        SET state = 'rolled_back', error_code = %s, owner_id = NULL,
            lease_expires_at = NULL, updated_at = %s
        WHERE operation = %s AND idempotency_key = %s
          AND state = 'pending' AND owner_id = %s
        RETURNING state
        """,
        [error_code, now, operation, idempotency_key, owner_id],
    ).fetchone()
    if row is None:
        raise IdempotencyConflictError("idempotency claim is not owned")


def append_annotation_revision(
    connection: psycopg.Connection,
    *,
    annotation_id: str,
    sample_id: str,
    article_id: str,
    security_id: str,
    final_value: str,
    suggestion_value: str,
    evidence_json: str,
    rule_version: str,
    actor: str,
    note: str | None,
    created_at: datetime,
    discovery_provenance_json: str | None = None,
) -> AnnotationRevisionRecord:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("created_at must be timezone-aware")
    sample_identity = connection.execute(
        """
        SELECT article_id, security_id, provenance_json
        FROM intelligence_samples WHERE sample_id = %s
        """,
        [sample_id],
    ).fetchone()
    if sample_identity is None:
        raise ValueError("annotation sample does not exist")
    if sample_identity[:2] != (article_id, security_id):
        raise ValueError("annotation sample identity mismatch")
    frozen_discovery_provenance = discovery_provenance_json or sample_identity[2]
    previous = connection.execute(
        """
        SELECT annotation_id, revision
        FROM intelligence_relevance_revisions
        WHERE sample_id = %s
        ORDER BY revision DESC
        LIMIT 1
        """,
        [sample_id],
    ).fetchone()
    previous_annotation_id = previous[0] if previous else None
    revision = int(previous[1]) + 1 if previous else 1
    connection.execute(
        """
        INSERT INTO intelligence_relevance_revisions (
            annotation_id, sample_id, article_id, security_id, revision, previous_annotation_id,
            final_value, suggestion_value, evidence_json, rule_version,
            actor, note, created_at, discovery_provenance_json
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        [
            annotation_id,
            sample_id,
            article_id,
            security_id,
            revision,
            previous_annotation_id,
            final_value,
            suggestion_value,
            evidence_json,
            rule_version,
            actor,
            note,
            created_at,
            frozen_discovery_provenance,
        ],
    )
    return AnnotationRevisionRecord(
        annotation_id=annotation_id,
        sample_id=sample_id,
        article_id=article_id,
        security_id=security_id,
        revision=revision,
        previous_annotation_id=previous_annotation_id,
        final_value=final_value,
        suggestion_value=suggestion_value,
        evidence_json=evidence_json,
        rule_version=rule_version,
        actor=actor,
        note=note,
        created_at=created_at,
    )


def list_annotation_revisions(
    connection: psycopg.Connection,
    *,
    sample_id: str,
) -> tuple[AnnotationRevisionRecord, ...]:
    rows = connection.execute(
        """
        SELECT annotation_id, sample_id, article_id, security_id, revision, previous_annotation_id,
               final_value, suggestion_value, evidence_json, rule_version,
               actor, note, created_at
        FROM intelligence_relevance_revisions
        WHERE sample_id = %s
        ORDER BY revision
        """,
        [sample_id],
    ).fetchall()
    return tuple(
        AnnotationRevisionRecord(
            annotation_id=row[0],
            sample_id=row[1],
            article_id=row[2],
            security_id=row[3],
            revision=row[4],
            previous_annotation_id=row[5],
            final_value=row[6],
            suggestion_value=row[7],
            evidence_json=row[8],
            rule_version=row[9],
            actor=row[10],
            note=row[11],
            created_at=row[12],
        )
        for row in rows
    )


def persist_dataset_snapshot(
    connection: psycopg.Connection,
    *,
    dataset_id: str,
    purpose: str,
    cohort: str,
    snapshot_checksum: str,
    manifest_json: str,
    members: tuple[dict[str, Any], ...],
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO intelligence_datasets (
            dataset_id, purpose, cohort, snapshot_checksum, manifest_json, created_at
        ) VALUES (%s, %s, %s, %s, %s, %s)
        """,
        [dataset_id, purpose, cohort, snapshot_checksum, manifest_json, created_at],
    )
    with connection.cursor() as cursor:
        cursor.executemany(
            """
            INSERT INTO intelligence_dataset_members (
                dataset_id, member_ordinal, sample_id, article_id, security_id,
                annotation_id, row_json
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                [
                    dataset_id,
                    ordinal,
                    member["sample_id"],
                    member["article_id"],
                    member["security_id"],
                    member["annotation_id"],
                    json.dumps(
                        member,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ]
                for ordinal, member in enumerate(members, start=1)
            ],
        )


def load_dataset_payload(
    connection: psycopg.Connection,
    *,
    dataset_id: str,
) -> str | None:
    row = connection.execute(
        "SELECT manifest_json FROM intelligence_datasets WHERE dataset_id = %s",
        [dataset_id],
    ).fetchone()
    return row[0] if row else None


def upsert_sample(
    connection: psycopg.Connection, *, sample: SampleRecord, created_at: datetime
) -> None:
    expected_basis = {
        "live_first_seen": "first_seen_at",
        "historical_publication_proxy": "published_at_proxy",
    }.get(sample.cohort)
    if expected_basis is None or sample.anchor_basis != expected_basis:
        raise ValueError("sample anchor basis does not match cohort")
    for value in (sample.published_at, sample.effective_label_anchor, created_at):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("sample timestamps must be timezone-aware")
    if sample.sample_origin not in {"event_selected", "random_control"}:
        raise ValueError("unsupported sample origin")
    connection.execute(
        """
        INSERT INTO intelligence_samples (
            sample_id, article_id, security_id, market, symbol, title, description,
            published_at, effective_label_anchor, anchor_basis, cohort,
            provenance_json, reaction_class, reaction_exclusion_reason,
            sample_origin, beta, abnormal_return, abnormal_return_std,
            turnover_zscore, created_at
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT (sample_id) DO UPDATE SET
            provenance_json = excluded.provenance_json,
            reaction_class = excluded.reaction_class,
            reaction_exclusion_reason = excluded.reaction_exclusion_reason,
            beta = excluded.beta,
            abnormal_return = excluded.abnormal_return,
            abnormal_return_std = excluded.abnormal_return_std,
            turnover_zscore = excluded.turnover_zscore
        """,
        [
            sample.sample_id,
            sample.article_id,
            sample.security_id,
            sample.market,
            sample.symbol,
            sample.title,
            sample.description,
            sample.published_at,
            sample.effective_label_anchor,
            sample.anchor_basis,
            sample.cohort,
            sample.provenance_json,
            sample.reaction_class,
            sample.reaction_exclusion_reason,
            sample.sample_origin,
            sample.beta,
            sample.abnormal_return,
            sample.abnormal_return_std,
            sample.turnover_zscore,
            created_at,
        ],
    )


def load_sample(
    connection: psycopg.Connection, *, sample_id: str
) -> SampleRecord | None:
    row = connection.execute(
        """
        SELECT sample_id, article_id, security_id, market, symbol, title, description,
               published_at, effective_label_anchor,
               anchor_basis, cohort, provenance_json, reaction_class,
               reaction_exclusion_reason, sample_origin,
               beta, abnormal_return, abnormal_return_std, turnover_zscore
        FROM intelligence_samples WHERE sample_id = %s
        """,
        [sample_id],
    ).fetchone()
    if row is None:
        return None
    return SampleRecord(
        sample_id=row[0],
        article_id=row[1],
        security_id=row[2],
        market=row[3],
        symbol=row[4],
        title=row[5],
        description=row[6],
        published_at=row[7],
        effective_label_anchor=row[8],
        anchor_basis=row[9],
        cohort=row[10],
        provenance_json=row[11],
        reaction_class=row[12],
        reaction_exclusion_reason=row[13],
        sample_origin=row[14],
        beta=row[15],
        abnormal_return=row[16],
        abnormal_return_std=row[17],
        turnover_zscore=row[18],
    )


def load_authoritative_candidates(
    connection: psycopg.Connection,
    *,
    annotation_ids: tuple[str, ...],
) -> tuple[dict[str, Any], ...]:
    result: list[dict[str, Any]] = []
    for annotation_id in annotation_ids:
        row = connection.execute(
            """
            SELECT s.sample_id, s.article_id, s.security_id, r.annotation_id,
                   r.final_value, s.effective_label_anchor,
                   s.anchor_basis, s.cohort, s.market, s.symbol,
                   s.reaction_class, s.reaction_exclusion_reason,
                   r.discovery_provenance_json,
                   r.revision, r.suggestion_value, r.evidence_json, r.rule_version,
                   r.actor, r.note, r.created_at, s.sample_origin,
                   s.abnormal_return, s.abnormal_return_std, s.beta, s.turnover_zscore,
                   s.title, s.description
            FROM intelligence_relevance_revisions r
            JOIN intelligence_samples s ON s.sample_id = r.sample_id
            WHERE r.annotation_id = %s
            """,
            [annotation_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"unknown annotation revision: {annotation_id}")
        latest = connection.execute(
            """
            SELECT annotation_id FROM intelligence_relevance_revisions
            WHERE sample_id = %s ORDER BY revision DESC LIMIT 1
            """,
            [row[0]],
        ).fetchone()
        if latest is None or latest[0] != annotation_id:
            raise ValueError(f"annotation revision is not current: {annotation_id}")
        provenance = json.loads(row[12])
        provenance["annotation_revision_id"] = annotation_id
        annotation = {
            "annotation_id": row[3],
            "revision": row[13],
            "final_value": row[4],
            "suggestion_value": row[14],
            "evidence": json.loads(row[15]),
            "rule_version": row[16],
            "actor": row[17],
            "note": row[18],
            "created_at": row[19].isoformat(),
        }
        result.append(
            {
                "sample_id": row[0],
                "article_id": row[1],
                "security_id": row[2],
                "annotation_id": row[3],
                "final_value": row[4],
                "effective_label_anchor": row[5],
                "anchor_basis": row[6],
                "cohort": row[7],
                "market": row[8],
                "symbol": row[9],
                "reaction_class": row[10],
                "reaction_exclusion_reason": row[11],
                "sample_origin": row[20],
                "abnormal_return": row[21],
                "abnormal_return_std": row[22],
                "beta": row[23],
                "turnover_zscore": row[24],
                "title": row[25],
                "description": row[26],
                "provenance": provenance,
                "annotation": annotation,
            }
        )
    return tuple(result)


def claim_export_artifact(
    connection: psycopg.Connection,
    *,
    export_id: str,
    dataset_id: str,
    sink: str,
    expected_path: str,
    expected_checksum: str,
    now: datetime,
) -> ExportRecord:
    row = connection.execute(
        """
        SELECT export_id, dataset_id, sink, state, expected_path, expected_checksum,
               artifact_checksum, error_code
        FROM intelligence_exports
        WHERE dataset_id = %s AND sink = %s AND expected_path = %s
        """,
        [dataset_id, sink, expected_path],
    ).fetchone()
    if row is not None:
        if row[5] != expected_checksum:
            raise IdempotencyConflictError("export artifact checksum conflict")
        return ExportRecord(*row)
    connection.execute(
        """
        INSERT INTO intelligence_exports (
            export_id, dataset_id, sink, state, expected_path, expected_checksum,
            created_at, updated_at
        ) VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s)
        """,
        [export_id, dataset_id, sink, expected_path, expected_checksum, now, now],
    )
    return ExportRecord(
        export_id,
        dataset_id,
        sink,
        "pending",
        expected_path,
        expected_checksum,
        None,
        None,
    )


def finish_export_artifact(
    connection: psycopg.Connection,
    *,
    export_id: str,
    artifact_checksum: str | None,
    error_code: str | None,
    now: datetime,
) -> None:
    state = "succeeded" if error_code is None else "failed"
    connection.execute(
        """
        UPDATE intelligence_exports
        SET state = %s, artifact_checksum = %s, error_code = %s, updated_at = %s
        WHERE export_id = %s
        """,
        [state, artifact_checksum, error_code, now, export_id],
    )


def list_exports(
    connection: psycopg.Connection, *, dataset_id: str
) -> tuple[ExportRecord, ...]:
    rows = connection.execute(
        """
        SELECT export_id, dataset_id, sink, state, expected_path, expected_checksum,
               artifact_checksum, error_code
        FROM intelligence_exports WHERE dataset_id = %s ORDER BY sink, expected_path
        """,
        [dataset_id],
    ).fetchall()
    return tuple(ExportRecord(*row) for row in rows)
