from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import hashlib

import psycopg
import pytest

from modules.domain.news_intelligence import KST
from modules.news.intelligence.processors.snapshot import build_dataset_snapshot
from modules.news.intelligence.processors.snapshot import snapshot_json_bytes
from modules.news.intelligence.processors.snapshot import snapshot_csv_bytes
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.catalog import load_catalog_snapshot
from modules.storage.news_intelligence.writer import SingleWriter
from modules.storage.news_intelligence.repositories import (
    SampleRecord,
    append_annotation_revision,
    upsert_sample,
    claim_export_artifact,
)
from tests.news_intelligence.test_discovery_slice import (
    _FakeMinuteMarketData,
    _catalog_database,
)


def test_snapshot_is_stably_ordered_partitioned_and_purpose_filtered() -> None:
    relevant = _candidate("b", "ann-2", "relevant")
    uncertain = _candidate("a", "ann-1", "uncertain")

    snapshot = build_dataset_snapshot(
        dataset_id="dataset-1",
        purpose="relevance_training",
        cohort="historical_publication_proxy",
        candidates=(relevant, uncertain),
    )

    assert [row["article_id"] for row in snapshot.members] == ["b"]
    assert snapshot.exclusions == (
        {"article_id": "a", "reason": "uncertain_relevance"},
    )
    assert snapshot.manifest["member_annotation_revision_ids"] == ["ann-2"]

    combined = build_dataset_snapshot(
        dataset_id="dataset-2",
        purpose="combined",
        cohort="historical_publication_proxy",
        candidates=(uncertain,),
    )
    assert combined.members == ()
    assert combined.exclusions[0]["reason"] == "uncertain_relevance"


def test_snapshot_groups_events_and_assigns_leakage_safe_splits() -> None:
    from datetime import timedelta

    base = datetime(2026, 6, 17, 9, 30, tzinfo=KST)

    def at(article_id: str, anchor, origin="event_selected"):
        return {
            **_candidate(article_id, f"ann-{article_id}", "relevant"),
            "effective_label_anchor": anchor,
            "sample_origin": origin,
        }

    near_a = at("a", base)
    near_b = at("b", base + timedelta(minutes=25))  # same event as a (gap 25 <= 30)
    far_c = at("c", base + timedelta(minutes=120))  # separate event
    control = at("d", base + timedelta(minutes=200), origin="random_control")

    snapshot = build_dataset_snapshot(
        dataset_id="dataset-split",
        purpose="relevance_training",
        cohort="historical_publication_proxy",
        candidates=(near_a, near_b, far_c, control),
        event_horizon_minutes=30,
    )

    members = {row["article_id"]: row for row in snapshot.members}
    assert members["a"]["event_id"] == members["b"]["event_id"]
    assert members["a"]["split"] == members["b"]["split"]  # no cross-fold leakage
    assert members["a"]["event_id"] != members["c"]["event_id"]
    assert all("split" in row for row in snapshot.members)

    manifest = snapshot.manifest
    assert manifest["schema_version"] == "news-intelligence-dataset-v3"
    assert manifest["event_count"] == 3
    assert sum(manifest["split_counts"].values()) == manifest["included_count"] == 4
    assert manifest["origin_counts"] == {"event_selected": 3, "random_control": 1}
    assert manifest["split_config"]["event_horizon_minutes"] == 30


def test_snapshot_stores_continuous_label_cross_section_and_surge() -> None:
    from datetime import timedelta
    from decimal import Decimal

    base = datetime(2026, 6, 17, 9, 30, tzinfo=KST)

    def reaction_candidate(article_id, anchor, abnormal, std, security="KOSDAQ:123456"):
        candidate = {
            **_candidate(article_id, f"ann-{article_id}", "relevant"),
            "effective_label_anchor": anchor,
            "security_id": security,
            "reaction_class": "positive",
            "reaction_exclusion_reason": None,
            "abnormal_return": Decimal(abnormal),
            "abnormal_return_std": Decimal(std),
            "beta": Decimal("1.2"),
            "turnover_zscore": Decimal("2.5"),
        }
        return candidate

    # Three names on the same day -> cross-sectional standardization is defined;
    # std values straddle the surge threshold (2.0).
    a = reaction_candidate("a", base, "0.01", "1.0", "KOSDAQ:111111")
    b = reaction_candidate("b", base + timedelta(minutes=1), "0.05", "2.5", "KOSDAQ:222222")
    c = reaction_candidate("c", base + timedelta(minutes=2), "0.09", "3.0", "KOSDAQ:333333")
    # A sample missing the standardized target must be excluded from reaction data.
    no_std = {
        **_candidate("d", "ann-d", "relevant"),
        "effective_label_anchor": base,
        "security_id": "KOSDAQ:444444",
        "reaction_class": "positive",
        "reaction_exclusion_reason": None,
        "abnormal_return": Decimal("0.04"),
        "abnormal_return_std": None,
    }

    snapshot = build_dataset_snapshot(
        dataset_id="dataset-surge",
        purpose="reaction_training",
        cohort="historical_publication_proxy",
        candidates=(a, b, c, no_std),
        surge_threshold_std=Decimal("2"),
    )

    members = {row["article_id"]: row for row in snapshot.members}
    assert set(members) == {"a", "b", "c"}  # no_std excluded
    assert snapshot.exclusions == ({"article_id": "d", "reason": "reaction_std_unavailable"},)
    # Continuous primary label is carried as a canonical string.
    assert members["b"]["abnormal_return_std"] == "2.5"
    # Cross-sectional standardization is defined (>=2 names that day, non-zero spread).
    assert all(members[a]["abnormal_return_std_xs"] is not None for a in ("a", "b", "c"))
    # Surge target derived from the time-series standardized value at threshold 2.0.
    assert members["a"]["surge_label"] == 0
    assert members["b"]["surge_label"] == 1
    assert members["c"]["surge_label"] == 1
    assert snapshot.manifest["surge_count"] == 2
    assert snapshot.manifest["label_config"]["primary_target"] == "abnormal_return_std"


def test_snapshot_rejects_unsupported_labels_and_mismatched_anchor_basis() -> None:
    candidate = _candidate("article", "ann", "invented")
    with pytest.raises(ValueError, match="unsupported final"):
        build_dataset_snapshot(
            dataset_id="dataset-invalid",
            purpose="combined",
            cohort="historical_publication_proxy",
            candidates=(candidate,),
        )
    with pytest.raises(ValueError, match="anchor basis"):
        build_dataset_snapshot(
            dataset_id="dataset-invalid",
            purpose="combined",
            cohort="historical_publication_proxy",
            candidates=(
                {
                    **_candidate("article", "ann", "relevant"),
                    "anchor_basis": "first_seen_at",
                },
            ),
        )


def test_one_frozen_snapshot_replays_and_exports_db_json_csv_manifest(
    tmp_path: Path,
    intelligence_dsn: str,
) -> None:
    services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        annotation_writer=SingleWriter(intelligence_dsn),
        export_root=tmp_path / "exports",
    )
    candidate = _candidate("article-1", "ann-frozen", "relevant")
    _persist_candidate(services.annotation_writer, candidate)

    first = asyncio.run(
        services.freeze_dataset(
            idempotency_key="freeze-1",
            dataset_id="dataset-1",
            purpose="combined",
            cohort="historical_publication_proxy",
            annotation_ids=("ann-frozen",),
        )
    )
    replay = asyncio.run(
        services.freeze_dataset(
            idempotency_key="freeze-1",
            dataset_id="dataset-1",
            purpose="combined",
            cohort="historical_publication_proxy",
            annotation_ids=("ann-frozen",),
        )
    )
    exported = asyncio.run(
        services.export_dataset(
            idempotency_key="export-1",
            dataset_id="dataset-1",
            sinks=("db", "json", "csv"),
        )
    )

    assert replay.snapshot.snapshot_checksum == first.snapshot.snapshot_checksum
    assert [sink.state for sink in exported.sinks] == ["succeeded"] * 3
    assert (tmp_path / "exports/dataset-1/dataset-1.json").is_file()
    assert (tmp_path / "exports/dataset-1/dataset-1.csv").is_file()
    manifest = json.loads(
        (tmp_path / "exports/dataset-1/dataset-1.manifest.json").read_text()
    )
    assert manifest["manifest"]["snapshot_checksum"] == first.snapshot.snapshot_checksum
    with psycopg.connect(intelligence_dsn) as connection:
        frozen_annotation = connection.execute(
            "SELECT annotation_id FROM intelligence_dataset_members"
        ).fetchone()[0]
    assert frozen_annotation == "ann-frozen"
    member = first.snapshot.members[0]
    assert member["annotation"] == {
        "actor": "tester",
        "annotation_id": "ann-frozen",
        "created_at": "2026-06-17T09:00:00+09:00",
        "evidence": [],
        "final_value": "relevant",
        "note": None,
        "revision": 1,
        "rule_version": "literal-direct-mention-v1",
        "suggestion_value": "relevant",
    }
    assert "annotation_json" in snapshot_csv_bytes(first.snapshot).decode("utf-8")


def test_freeze_rejects_forged_and_stale_annotation_revisions(
    tmp_path: Path, intelligence_dsn: str
) -> None:
    services = _services(tmp_path, intelligence_dsn)
    candidate = _candidate("article-1", "ann-1", "relevant")
    _persist_candidate(services.annotation_writer, candidate)
    writer = services.annotation_writer
    assert writer is not None
    writer.execute(
        lambda connection: append_annotation_revision(
            connection,
            annotation_id="ann-2",
            sample_id=candidate["sample_id"],
            article_id=candidate["article_id"],
            security_id=candidate["security_id"],
            final_value="not_relevant",
            suggestion_value="relevant",
            evidence_json="[]",
            rule_version="literal-direct-mention-v1",
            actor="reviewer",
            note=None,
            created_at=datetime(2026, 6, 17, 1, tzinfo=timezone.utc),
        )
    )

    with pytest.raises(ValueError, match="not current"):
        asyncio.run(
            services.freeze_dataset(
                idempotency_key="stale",
                dataset_id="stale",
                purpose="combined",
                cohort="historical_publication_proxy",
                annotation_ids=("ann-1",),
            )
        )
    with pytest.raises(ValueError, match="unknown annotation"):
        asyncio.run(
            services.freeze_dataset(
                idempotency_key="forged",
                dataset_id="forged",
                purpose="combined",
                cohort="historical_publication_proxy",
                annotation_ids=("does-not-exist",),
            )
        )


def test_dataset_accepts_same_article_for_distinct_security_samples(
    tmp_path: Path,
    intelligence_dsn: str,
) -> None:
    services = _services(tmp_path, intelligence_dsn)
    first = _candidate("shared-article", "ann-a", "relevant")
    second = {
        **_candidate("shared-article", "ann-b", "relevant"),
        "sample_id": "sample-second-security",
        "security_id": "KOSPI:654321",
        "market": "KOSPI",
        "symbol": "654321",
    }
    _persist_candidate(services.annotation_writer, first)
    _persist_candidate(services.annotation_writer, second)
    result = asyncio.run(
        services.freeze_dataset(
            idempotency_key="multi",
            dataset_id="multi",
            purpose="relevance_training",
            cohort="historical_publication_proxy",
            annotation_ids=("ann-a", "ann-b"),
        )
    )
    assert len(result.snapshot.members) == 2


def test_export_recovers_pending_record_after_atomic_rename(
    tmp_path: Path, intelligence_dsn: str
) -> None:
    services = _services(tmp_path, intelligence_dsn)
    candidate = _candidate("article", "ann", "relevant")
    _persist_candidate(services.annotation_writer, candidate)
    frozen = asyncio.run(
        services.freeze_dataset(
            idempotency_key="freeze",
            dataset_id="recover",
            purpose="relevance_training",
            cohort="historical_publication_proxy",
            annotation_ids=("ann",),
        )
    )
    content = snapshot_json_bytes(frozen.snapshot)
    path = tmp_path / "exports/recover/recover.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    writer = services.annotation_writer
    assert writer is not None
    writer.execute(
        lambda connection: claim_export_artifact(
            connection,
            export_id="pending-export",
            dataset_id="recover",
            sink="json",
            expected_path="recover/recover.json",
            expected_checksum=hashlib.sha256(content).hexdigest(),
            now=datetime(2026, 6, 17, tzinfo=timezone.utc),
        )
    )

    result = asyncio.run(
        services.export_dataset(
            idempotency_key="recover-export",
            dataset_id="recover",
            sinks=("json",),
        )
    )
    assert result.sinks[0].state == "succeeded"
    assert result.sinks[0].artifact_checksums == (hashlib.sha256(content).hexdigest(),)


def test_export_reports_checksum_conflict_per_sink_and_can_retry(
    tmp_path: Path,
    intelligence_dsn: str,
) -> None:
    services = _services(tmp_path, intelligence_dsn)
    candidate = _candidate("article", "ann", "relevant")
    _persist_candidate(services.annotation_writer, candidate)
    asyncio.run(
        services.freeze_dataset(
            idempotency_key="freeze",
            dataset_id="conflict",
            purpose="relevance_training",
            cohort="historical_publication_proxy",
            annotation_ids=("ann",),
        )
    )
    path = tmp_path / "exports/conflict/conflict.json"
    path.parent.mkdir(parents=True)
    path.write_text("tampered")
    failed = asyncio.run(
        services.export_dataset(
            idempotency_key="export-1",
            dataset_id="conflict",
            sinks=("json",),
        )
    )
    assert failed.sinks[0].state == "failed"
    assert failed.sinks[0].error_code == "artifact_checksum_conflict"
    path.unlink()
    retried = asyncio.run(
        services.export_dataset(
            idempotency_key="export-2",
            dataset_id="conflict",
            sinks=("json",),
        )
    )
    assert retried.sinks[0].state == "succeeded"


def test_failed_dataset_freeze_rolls_back_idempotency_claim(
    tmp_path: Path, intelligence_dsn: str
) -> None:
    services = _services(tmp_path, intelligence_dsn)
    candidate = _candidate("article", "ann", "relevant")
    _persist_candidate(services.annotation_writer, candidate)
    asyncio.run(
        services.freeze_dataset(
            idempotency_key="first-freeze",
            dataset_id="same-dataset",
            purpose="relevance_training",
            cohort="historical_publication_proxy",
            annotation_ids=("ann",),
        )
    )

    with pytest.raises(Exception):
        asyncio.run(
            services.freeze_dataset(
                idempotency_key="conflicting-freeze",
                dataset_id="same-dataset",
                purpose="combined",
                cohort="historical_publication_proxy",
                annotation_ids=("ann",),
            )
        )

    writer = services.annotation_writer
    assert writer is not None
    state = writer.read(
        lambda connection: connection.execute(
            """
            SELECT state, error_code FROM intelligence_idempotency
            WHERE operation = 'dataset.freeze' AND idempotency_key = %s
            """,
            ["conflicting-freeze"],
        ).fetchone()
    )
    assert state == ("rolled_back", "dataset_freeze_failed")


def _candidate(article_id: str, annotation_id: str, final_value: str):
    return {
        "sample_id": f"sample-{article_id}",
        "article_id": article_id,
        "security_id": "KOSDAQ:123456",
        "annotation_id": annotation_id,
        "final_value": final_value,
        "effective_label_anchor": datetime(2026, 6, 17, 9, 30, tzinfo=KST),
        "anchor_basis": "published_at_proxy",
        "cohort": "historical_publication_proxy",
        "market": "KOSDAQ",
        "symbol": "123456",
        "reaction_class": None,
        "reaction_exclusion_reason": "benchmark_unavailable",
        "provenance": {
            "catalog_snapshot_id": "catalog-1",
            "discovery_plan_version": "naver-discovery-plan-v1",
            "annotation_revision_id": annotation_id,
        },
        "annotation": {
            "annotation_id": annotation_id,
            "revision": 1,
            "final_value": final_value,
            "suggestion_value": "relevant",
            "evidence": [],
            "rule_version": "literal-direct-mention-v1",
            "actor": "tester",
            "note": None,
            "created_at": "2026-06-17T00:00:00+00:00",
        },
    }


def _persist_candidate(writer: SingleWriter | None, candidate) -> None:
    assert writer is not None
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)

    def mutation(connection):
        upsert_sample(
            connection,
            sample=SampleRecord(
                sample_id=candidate["sample_id"],
                article_id=candidate["article_id"],
                security_id=candidate["security_id"],
                market=candidate["market"],
                symbol=candidate["symbol"],
                title="테스트기업 뉴스",
                description="설명",
                published_at=candidate["effective_label_anchor"],
                effective_label_anchor=candidate["effective_label_anchor"],
                anchor_basis=candidate["anchor_basis"],
                cohort=candidate["cohort"],
                provenance_json=json.dumps(candidate["provenance"]),
                reaction_class=candidate["reaction_class"],
                reaction_exclusion_reason=candidate["reaction_exclusion_reason"],
            ),
            created_at=now,
        )
        append_annotation_revision(
            connection,
            annotation_id=candidate["annotation_id"],
            sample_id=candidate["sample_id"],
            article_id=candidate["article_id"],
            security_id=candidate["security_id"],
            final_value=candidate["final_value"],
            suggestion_value="relevant",
            evidence_json="[]",
            rule_version="literal-direct-mention-v1",
            actor="tester",
            note=None,
            created_at=now,
        )

    writer.execute(mutation)


def _services(tmp_path: Path, intelligence_dsn: str) -> NewsIntelligenceServices:
    return NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        annotation_writer=SingleWriter(intelligence_dsn),
        export_root=tmp_path / "exports",
    )
