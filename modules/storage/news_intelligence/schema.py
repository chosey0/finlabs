"""Idempotent PostgreSQL schema migrations for news intelligence."""

from __future__ import annotations

from collections.abc import Iterable

import psycopg

SCHEMA_VERSION = 4

_MIGRATIONS: tuple[tuple[int, tuple[str, ...]], ...] = (
    (
        1,
        (
            """
            CREATE TABLE IF NOT EXISTS intelligence_idempotency (
                operation VARCHAR NOT NULL,
                idempotency_key VARCHAR NOT NULL,
                request_hash VARCHAR NOT NULL,
                state VARCHAR NOT NULL CHECK (state IN ('pending', 'succeeded', 'rolled_back')),
                owner_id VARCHAR,
                lease_expires_at TIMESTAMPTZ,
                result_ref VARCHAR,
                error_code VARCHAR,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                PRIMARY KEY (operation, idempotency_key)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS intelligence_annotations (
                annotation_id VARCHAR PRIMARY KEY,
                article_id VARCHAR NOT NULL,
                revision INTEGER NOT NULL,
                label VARCHAR NOT NULL CHECK (label IN ('relevant', 'not_relevant', 'unresolved')),
                actor VARCHAR NOT NULL,
                note VARCHAR,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (article_id, revision)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS intelligence_datasets (
                dataset_id VARCHAR PRIMARY KEY,
                purpose VARCHAR NOT NULL,
                cohort VARCHAR NOT NULL,
                snapshot_checksum VARCHAR NOT NULL UNIQUE,
                manifest_json VARCHAR NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS intelligence_dataset_members (
                dataset_id VARCHAR NOT NULL,
                member_ordinal INTEGER NOT NULL,
                article_id VARCHAR NOT NULL,
                annotation_id VARCHAR,
                row_json VARCHAR NOT NULL,
                PRIMARY KEY (dataset_id, member_ordinal),
                UNIQUE (dataset_id, article_id)
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS intelligence_exports (
                export_id VARCHAR PRIMARY KEY,
                dataset_id VARCHAR NOT NULL,
                sink VARCHAR NOT NULL,
                state VARCHAR NOT NULL CHECK (state IN ('pending', 'succeeded', 'failed')),
                expected_path VARCHAR,
                expected_checksum VARCHAR,
                artifact_checksum VARCHAR,
                error_code VARCHAR,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                UNIQUE (dataset_id, sink, expected_path)
            )
            """,
        ),
    ),
    (
        2,
        (
            """
            CREATE TABLE IF NOT EXISTS intelligence_relevance_revisions (
                annotation_id VARCHAR PRIMARY KEY,
                article_id VARCHAR NOT NULL,
                revision INTEGER NOT NULL,
                previous_annotation_id VARCHAR,
                final_value VARCHAR NOT NULL CHECK (
                    final_value IN ('relevant', 'not_relevant', 'uncertain')
                ),
                suggestion_value VARCHAR NOT NULL CHECK (
                    suggestion_value IN ('relevant', 'unresolved')
                ),
                evidence_json VARCHAR NOT NULL,
                rule_version VARCHAR NOT NULL,
                actor VARCHAR NOT NULL,
                note VARCHAR,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (article_id, revision)
            )
            """,
        ),
    ),
    (
        3,
        (
            """
            CREATE TABLE IF NOT EXISTS intelligence_samples (
                sample_id VARCHAR PRIMARY KEY,
                article_id VARCHAR NOT NULL,
                security_id VARCHAR NOT NULL,
                market VARCHAR NOT NULL,
                symbol VARCHAR NOT NULL,
                title VARCHAR NOT NULL,
                description VARCHAR NOT NULL,
                published_at TIMESTAMPTZ NOT NULL,
                effective_label_anchor TIMESTAMPTZ NOT NULL,
                anchor_basis VARCHAR NOT NULL CHECK (
                    anchor_basis IN ('first_seen_at', 'published_at_proxy')
                ),
                cohort VARCHAR NOT NULL CHECK (
                    cohort IN ('live_first_seen', 'historical_publication_proxy')
                ),
                provenance_json VARCHAR NOT NULL,
                reaction_class VARCHAR,
                reaction_exclusion_reason VARCHAR,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (article_id, security_id, effective_label_anchor)
            )
            """,
            """
            CREATE TABLE intelligence_relevance_revisions_v3 (
                annotation_id VARCHAR PRIMARY KEY,
                sample_id VARCHAR NOT NULL,
                article_id VARCHAR NOT NULL,
                security_id VARCHAR NOT NULL,
                revision INTEGER NOT NULL,
                previous_annotation_id VARCHAR,
                final_value VARCHAR NOT NULL CHECK (
                    final_value IN ('relevant', 'not_relevant', 'uncertain')
                ),
                suggestion_value VARCHAR NOT NULL CHECK (
                    suggestion_value IN ('relevant', 'unresolved')
                ),
                evidence_json VARCHAR NOT NULL,
                rule_version VARCHAR NOT NULL,
                actor VARCHAR NOT NULL,
                note VARCHAR,
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (sample_id, revision)
            )
            """,
            """
            INSERT INTO intelligence_relevance_revisions_v3
            SELECT annotation_id, article_id, article_id, '', revision,
                   previous_annotation_id, final_value, suggestion_value,
                   evidence_json, rule_version, actor, note, created_at
            FROM intelligence_relevance_revisions
            """,
            "DROP TABLE intelligence_relevance_revisions",
            "ALTER TABLE intelligence_relevance_revisions_v3 RENAME TO intelligence_relevance_revisions",
            """
            CREATE TABLE intelligence_dataset_members_v3 (
                dataset_id VARCHAR NOT NULL,
                member_ordinal INTEGER NOT NULL,
                sample_id VARCHAR NOT NULL,
                article_id VARCHAR NOT NULL,
                security_id VARCHAR NOT NULL,
                annotation_id VARCHAR NOT NULL,
                row_json VARCHAR NOT NULL,
                PRIMARY KEY (dataset_id, member_ordinal),
                UNIQUE (dataset_id, sample_id)
            )
            """,
            """
            INSERT INTO intelligence_dataset_members_v3
            SELECT dataset_id, member_ordinal, article_id, article_id, '',
                   COALESCE(annotation_id, ''), row_json
            FROM intelligence_dataset_members
            """,
            "DROP TABLE intelligence_dataset_members",
            "ALTER TABLE intelligence_dataset_members_v3 RENAME TO intelligence_dataset_members",
        ),
    ),
    (
        4,
        (
            """
            ALTER TABLE intelligence_relevance_revisions
            ADD COLUMN discovery_provenance_json VARCHAR DEFAULT '{}'
            """,
            """
            UPDATE intelligence_relevance_revisions AS revision
            SET discovery_provenance_json = COALESCE(
                (
                    SELECT sample.provenance_json
                    FROM intelligence_samples AS sample
                    WHERE sample.sample_id = revision.sample_id
                ),
                '{}'
            )
            """,
        ),
    ),
)


def initialize_schema(connection: psycopg.Connection) -> tuple[int, ...]:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS intelligence_schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT current_timestamp
        )
        """
    )
    connection.commit()
    applied = {
        row[0]
        for row in connection.execute(
            "SELECT version FROM intelligence_schema_migrations"
        ).fetchall()
    }
    newly_applied: list[int] = []
    for version, statements in _MIGRATIONS:
        if version in applied:
            continue
        _apply_migration(connection, version, statements)
        newly_applied.append(version)
    return tuple(newly_applied)


def _apply_migration(
    connection: psycopg.Connection,
    version: int,
    statements: Iterable[str],
) -> None:
    try:
        for statement in statements:
            connection.execute(statement)
        connection.execute(
            "INSERT INTO intelligence_schema_migrations (version) VALUES (%s)",
            [version],
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
