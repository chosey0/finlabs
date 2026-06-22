from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from finlabs_intelligence.api.app import app
from finlabs_intelligence.api.export_openapi import export_openapi
from modules.domain.news_intelligence import (
    DatasetCohort,
    ObservationTime,
    TimeBasis,
)
from modules.storage.news_intelligence.database import connect
from modules.storage.news_intelligence.exports import (
    ExportArtifactConflictError,
    UnsafeExportPathError,
    resolve_export_path,
    write_or_reconcile,
)
from modules.storage.news_intelligence.locking import WRITE_LOCK_KEY
from modules.storage.news_intelligence.repositories import (
    ClaimDisposition,
    IdempotencyConflictError,
    canonical_request_hash,
    claim_operation,
    mark_operation_succeeded,
)
from modules.storage.news_intelligence.schema import initialize_schema
from modules.storage.news_intelligence.writer import SingleWriter, WriterQueueFullError


def test_observation_time_separates_canonical_live_t0_from_proxy() -> None:
    first_seen = datetime(2026, 6, 17, 10, 0, tzinfo=timezone.utc)
    published = datetime(2020, 1, 2, 3, 0, tzinfo=timezone.utc)

    live = ObservationTime(
        first_seen_at=first_seen,
        t0=first_seen,
        proxy_event_time=None,
        effective_label_anchor=first_seen,
        anchor_basis=TimeBasis.FIRST_SEEN_AT,
        cohort=DatasetCohort.LIVE_FIRST_SEEN,
    )
    historical = ObservationTime(
        first_seen_at=first_seen,
        t0=None,
        proxy_event_time=published,
        effective_label_anchor=published,
        anchor_basis=TimeBasis.PUBLISHED_AT_PROXY,
        cohort=DatasetCohort.HISTORICAL_PUBLICATION_PROXY,
    )

    assert live.t0 == first_seen
    assert historical.t0 is None


def test_schema_migration_is_idempotent_and_has_no_raw_candle_table(
    intelligence_dsn: str,
) -> None:
    connection = connect(intelligence_dsn)
    try:
        assert initialize_schema(connection) == (1, 2, 3, 4)
        assert initialize_schema(connection) == ()
        table_names = {
            row[0]
            for row in connection.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = current_schema()
                """
            ).fetchall()
        }
    finally:
        connection.close()

    assert "intelligence_annotations" in table_names
    assert not any(
        "candle" in table_name or "raw" in table_name for table_name in table_names
    )


def test_claim_replay_conflict_and_stale_takeover(intelligence_dsn: str) -> None:
    now = datetime(2026, 6, 17, 1, 0, tzinfo=timezone.utc)
    request_hash = canonical_request_hash({"article_id": "a1", "label": "relevant"})
    connection = connect(intelligence_dsn)
    try:
        initialize_schema(connection)
        first = claim_operation(
            connection,
            operation="annotation.create",
            idempotency_key="key-1",
            request_hash=request_hash,
            owner_id="owner-a",
            now=now,
            lease_duration=timedelta(minutes=1),
        )
        in_progress = claim_operation(
            connection,
            operation="annotation.create",
            idempotency_key="key-1",
            request_hash=request_hash,
            owner_id="owner-b",
            now=now + timedelta(seconds=30),
            lease_duration=timedelta(minutes=1),
        )
        takeover = claim_operation(
            connection,
            operation="annotation.create",
            idempotency_key="key-1",
            request_hash=request_hash,
            owner_id="owner-b",
            now=now + timedelta(minutes=2),
            lease_duration=timedelta(minutes=1),
        )
        connection.execute(
            """
            INSERT INTO intelligence_annotations
            VALUES ('ann-1', 'a1', 1, 'relevant', 'tester', NULL, %s)
            """,
            [now],
        )
        mark_operation_succeeded(
            connection,
            operation="annotation.create",
            idempotency_key="key-1",
            owner_id="owner-b",
            result_ref="ann-1",
            now=now + timedelta(minutes=2),
        )
        connection.commit()
        replay = claim_operation(
            connection,
            operation="annotation.create",
            idempotency_key="key-1",
            request_hash=request_hash,
            owner_id="owner-c",
            now=now + timedelta(minutes=3),
            lease_duration=timedelta(minutes=1),
        )
        with pytest.raises(IdempotencyConflictError):
            claim_operation(
                connection,
                operation="annotation.create",
                idempotency_key="key-1",
                request_hash=canonical_request_hash({"article_id": "other"}),
                owner_id="owner-c",
                now=now + timedelta(minutes=3),
                lease_duration=timedelta(minutes=1),
            )
    finally:
        connection.close()

    assert first.disposition is ClaimDisposition.ACQUIRED
    assert in_progress.disposition is ClaimDisposition.IN_PROGRESS
    assert takeover.disposition is ClaimDisposition.ACQUIRED
    assert replay.disposition is ClaimDisposition.REPLAY
    assert replay.result_ref == "ann-1"


@pytest.mark.parametrize("failure_point", ["after_business", "before_terminal"])
def test_business_and_terminal_result_rollback_together(
    intelligence_dsn: str, failure_point: str
) -> None:
    now = datetime.now(timezone.utc)
    request_hash = canonical_request_hash({"article": "a1"})
    setup = connect(intelligence_dsn)
    try:
        initialize_schema(setup)
        claim_operation(
            setup,
            operation="annotation.create",
            idempotency_key="atomic-key",
            request_hash=request_hash,
            owner_id="owner",
            now=now,
            lease_duration=timedelta(minutes=5),
        )
    finally:
        setup.close()

    writer = SingleWriter(intelligence_dsn)

    def mutation(connection: psycopg.Connection) -> None:
        connection.execute(
            """
            INSERT INTO intelligence_annotations
            VALUES ('ann-atomic', 'a1', 1, 'relevant', 'tester', NULL, %s)
            """,
            [now],
        )
        if failure_point == "after_business":
            raise RuntimeError("fault after business statement")
        if failure_point == "before_terminal":
            raise RuntimeError("fault before terminal state")
        mark_operation_succeeded(
            connection,
            operation="annotation.create",
            idempotency_key="atomic-key",
            owner_id="owner",
            result_ref="ann-atomic",
            now=now,
        )

    with pytest.raises(RuntimeError, match="fault"):
        writer.execute(mutation)
    writer.close()

    verify = connect(intelligence_dsn)
    try:
        business_count = verify.execute(
            "SELECT count(*) FROM intelligence_annotations"
        ).fetchone()[0]
        state = verify.execute(
            "SELECT state FROM intelligence_idempotency"
        ).fetchone()[0]
    finally:
        verify.close()

    assert business_count == 0
    assert state == "pending"


def test_single_writer_is_fifo_and_never_overlaps_transactions(
    intelligence_dsn: str,
) -> None:
    writer = SingleWriter(intelligence_dsn)
    accepted: list[int] = []
    completed: list[int] = []
    active = 0
    maximum_active = 0
    guard = threading.Lock()

    def task(index: int) -> None:
        nonlocal active, maximum_active
        with guard:
            accepted.append(index)

        def mutation(connection: psycopg.Connection) -> None:
            nonlocal active, maximum_active
            with guard:
                active += 1
                maximum_active = max(maximum_active, active)
            time.sleep(0.005)
            connection.execute("SELECT 1")
            with guard:
                active -= 1
                completed.append(index)

        writer.execute(mutation)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(task, index) for index in range(20)]
        for future in futures:
            future.result()
    writer.close()

    assert maximum_active == 1
    assert completed == accepted


def test_single_writer_applies_bounded_backpressure(intelligence_dsn: str) -> None:
    writer = SingleWriter(intelligence_dsn, max_pending=1)
    entered = threading.Event()
    release = threading.Event()

    def blocking_write() -> None:
        writer.execute(lambda connection: (entered.set(), release.wait(timeout=5)))

    thread = threading.Thread(target=blocking_write)
    thread.start()
    assert entered.wait(timeout=5)
    with pytest.raises(WriterQueueFullError, match="queue is full"):
        writer.execute(lambda connection: connection.execute("SELECT 1"))
    release.set()
    thread.join(timeout=5)
    assert not thread.is_alive()
    writer.close()


def test_advisory_lock_serializes_competing_writer_sessions(
    intelligence_dsn: str,
) -> None:
    holder = connect(intelligence_dsn)
    competitor = connect(intelligence_dsn)
    try:
        # The holder opens a write transaction and takes the shared write lock.
        holder.execute("SELECT pg_advisory_xact_lock(%s)", [WRITE_LOCK_KEY])
        # A second session (standing in for another process) cannot take it.
        blocked = competitor.execute(
            "SELECT pg_try_advisory_xact_lock(%s)", [WRITE_LOCK_KEY]
        ).fetchone()[0]
        assert blocked is False
        # Once the holder's transaction ends the lock is released.
        holder.rollback()
        acquired = competitor.execute(
            "SELECT pg_try_advisory_xact_lock(%s)", [WRITE_LOCK_KEY]
        ).fetchone()[0]
        assert acquired is True
    finally:
        competitor.rollback()
        holder.close()
        competitor.close()


def test_file_export_reconciles_match_and_rejects_mismatch(tmp_path: Path) -> None:
    target, checksum, reconciled = write_or_reconcile(
        root=tmp_path,
        relative_path="dataset/result.json",
        content=b'{"id":"d1"}\n',
    )
    same = write_or_reconcile(
        root=tmp_path,
        relative_path="dataset/result.json",
        content=b'{"id":"d1"}\n',
    )

    assert target.read_bytes() == b'{"id":"d1"}\n'
    assert same == (target, checksum, True)
    assert reconciled is False
    with pytest.raises(ExportArtifactConflictError):
        write_or_reconcile(
            root=tmp_path,
            relative_path="dataset/result.json",
            content=b"different",
        )
    with pytest.raises(UnsafeExportPathError):
        resolve_export_path(tmp_path, "../escape.json")


def test_openapi_export_is_deterministic_and_generator_is_exact_pinned(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    export_openapi(first)
    export_openapi(second)

    package = json.loads(
        (
            Path(__file__).parents[2] / "finlabs_intelligence/web/package.json"
        ).read_text()
    )
    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text()) == app.openapi()
    assert package["devDependencies"]["@hey-api/openapi-ts"] == "0.98.2"
    assert package["scripts"]["generate:api"] == "openapi-ts"
