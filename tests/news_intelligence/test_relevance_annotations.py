from __future__ import annotations

import json
from datetime import date, datetime, timezone
from dataclasses import replace

import psycopg
from fastapi.testclient import TestClient

from finlabs_intelligence.api.app import app
from modules.domain.news_intelligence import CatalogAlias, HistoricalNameStatus
from modules.news.intelligence.processors.relevance import suggest_direct_mention
from modules.orchestration.news_intelligence import NewsIntelligenceServices
from modules.storage.news_intelligence.repositories import (
    SampleRecord,
    append_annotation_revision,
    list_annotation_revisions,
    upsert_sample,
)
from modules.storage.news_intelligence.schema import initialize_schema
from modules.storage.news_intelligence.writer import SingleWriter
from tests.news_intelligence.test_discovery_slice import (
    _FakeMinuteMarketData,
    _catalog_database,
)
from modules.storage.news_intelligence.catalog import load_catalog_snapshot


def test_direct_mention_is_literal_normalized_versioned_and_never_auto_negative() -> (
    None
):
    aliases = (_alias("a-ko", "삼성전자"), _alias("a-en", "Samsung Electronics"))

    matched = suggest_direct_mention(
        title="[속보] 삼성전자  실적 발표",
        description="SAMSUNG ELECTRONICS outlook",
        aliases=aliases,
    )
    absent = suggest_direct_mention(
        title="반도체 업황",
        description="시장 전망",
        aliases=aliases,
    )

    assert matched.value == "relevant"
    assert matched.rule_version == "literal-direct-mention-v1"
    assert [(row.field, row.alias_id) for row in matched.evidence] == [
        ("description", "a-en"),
        ("title", "a-ko"),
    ]
    assert absent.value == "unresolved"
    assert absent.evidence == ()


def test_human_annotation_edits_append_authoritative_revision_history(
    intelligence_dsn: str,
) -> None:
    writer = SingleWriter(intelligence_dsn)
    now = datetime(2026, 6, 17, tzinfo=timezone.utc)
    writer.execute(
        lambda connection: upsert_sample(
            connection,
            sample=replace(_sample(), sample_id="sample-1", article_id="article-1"),
            created_at=now,
        )
    )

    first = writer.execute(
        lambda connection: append_annotation_revision(
            connection,
            annotation_id="ann-1",
            sample_id="sample-1",
            article_id="article-1",
            security_id="KOSDAQ:123456",
            final_value="relevant",
            suggestion_value="relevant",
            evidence_json=json.dumps([{"alias_id": "a-ko"}], sort_keys=True),
            rule_version="literal-direct-mention-v1",
            actor="analyst",
            note="direct mention confirmed",
            created_at=now,
        )
    )
    second = writer.execute(
        lambda connection: append_annotation_revision(
            connection,
            annotation_id="ann-2",
            sample_id="sample-1",
            article_id="article-1",
            security_id="KOSDAQ:123456",
            final_value="uncertain",
            suggestion_value="relevant",
            evidence_json=json.dumps([{"alias_id": "a-ko"}], sort_keys=True),
            rule_version="literal-direct-mention-v1",
            actor="reviewer",
            note="same-name company ambiguity",
            created_at=now,
        )
    )
    with psycopg.connect(intelligence_dsn) as connection:
        history = list_annotation_revisions(connection, sample_id="sample-1")

    assert first.revision == 1
    assert second.revision == 2
    assert second.previous_annotation_id == "ann-1"
    assert [row.final_value for row in history] == ["relevant", "uncertain"]
    assert history[-1].actor == "reviewer"


def test_schema_v3_is_forward_only_and_idempotent(intelligence_dsn: str) -> None:
    with psycopg.connect(intelligence_dsn) as connection:
        assert initialize_schema(connection) == (1, 2, 3, 4, 5, 6)
        assert initialize_schema(connection) == ()


def test_annotation_api_recomputes_suggestion_replays_and_appends_edits(
    intelligence_dsn: str,
) -> None:
    writer = SingleWriter(intelligence_dsn)
    writer.execute(
        lambda connection: upsert_sample(
            connection,
            sample=_sample(),
            created_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
        )
    )
    app.state.news_intelligence_services = NewsIntelligenceServices(
        catalog_snapshot=load_catalog_snapshot(_catalog_database(intelligence_dsn)),
        market_data=_FakeMinuteMarketData(),
        annotation_writer=writer,
    )
    client = TestClient(app)
    body = {
        "sample_id": "sample-api-1",
        "final_value": "relevant",
        "actor": "analyst",
        "note": "confirmed",
    }

    suggestion = client.post(
        "/api/relevance/suggest",
        json={
            "security_id": "KOSDAQ:123456",
            "title": "테스트기업 신규 계약",
            "description": "공급 계약을 체결했다.",
            "selected_on": "2026-06-17",
        },
    )
    first = client.post(
        "/api/annotations",
        headers={"Idempotency-Key": "annotation-api-1"},
        json=body,
    )
    replay = client.post(
        "/api/annotations",
        headers={"Idempotency-Key": "annotation-api-1"},
        json=body,
    )
    edited = client.post(
        "/api/annotations",
        headers={"Idempotency-Key": "annotation-api-2"},
        json={**body, "final_value": "uncertain", "actor": "reviewer"},
    )
    history = client.get("/api/annotations/sample-api-1")

    assert suggestion.status_code == 200
    assert suggestion.json()["value"] == "relevant"
    assert first.status_code == replay.status_code == edited.status_code == 200
    assert first.json()["annotation_id"] == replay.json()["annotation_id"]
    assert edited.json()["revision"] == 2
    assert edited.json()["previous_annotation_id"] == first.json()["annotation_id"]
    assert [item["final_value"] for item in history.json()] == [
        "relevant",
        "uncertain",
    ]


def _alias(alias_id: str, term: str) -> CatalogAlias:
    return CatalogAlias(
        alias_id=alias_id,
        term=term,
        valid_from=date.min,
        valid_to=None,
        source="test",
        historical_name_status=HistoricalNameStatus.CURRENT_ONLY,
    )


def _sample() -> SampleRecord:
    return SampleRecord(
        sample_id="sample-api-1",
        article_id="article-api-1",
        security_id="KOSDAQ:123456",
        market="KOSDAQ",
        symbol="123456",
        title="테스트기업 신규 계약",
        description="공급 계약을 체결했다.",
        published_at=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
        effective_label_anchor=datetime(2026, 6, 17, 9, 30, tzinfo=timezone.utc),
        anchor_basis="published_at_proxy",
        cohort="historical_publication_proxy",
        provenance_json=json.dumps({"catalog_snapshot_id": "catalog-1"}),
        reaction_class=None,
        reaction_exclusion_reason="benchmark_unavailable",
    )
