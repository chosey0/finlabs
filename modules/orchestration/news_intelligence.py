"""Use cases for catalog search and on-demand chart loading."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol

from modules.domain.news_intelligence import (
    CatalogSecurity,
    CatalogSnapshot,
    DiscoveredNewsArticle,
    IntelligenceCandle,
    KST,
    NewsArticleCandidate,
    NewsDiscoveryResult,
    ReactionSourceData,
    approved_kiwoom_benchmark,
    build_discovery_plan,
    candle_identity_checksum,
)
from modules.storage.news_intelligence.catalog import search_catalog
from modules.storage.news_intelligence.repositories import (
    AnnotationRevisionRecord,
    ClaimDisposition,
    IdempotencyConflictError,
    append_annotation_revision,
    claim_export_artifact,
    canonical_request_hash,
    claim_operation,
    finish_export_artifact,
    list_annotation_revisions,
    list_exports,
    load_authoritative_candidates,
    load_dataset_payload,
    load_sample,
    mark_operation_rolled_back,
    mark_operation_succeeded,
    persist_dataset_snapshot,
    SampleRecord,
    upsert_sample,
)
from modules.storage.news_intelligence.writer import SingleWriter
from modules.storage.news_intelligence.exports import (
    ExportArtifactConflictError,
    write_or_reconcile,
)
from modules.news.intelligence.processors.relevance import (
    RelevanceSuggestion,
    suggest_direct_mention,
)
from modules.news.intelligence.processors.reaction import (
    ReactionPreview,
    preview_reaction,
)
from modules.news.intelligence.processors.snapshot import (
    DatasetSnapshot,
    build_dataset_snapshot,
    snapshot_csv_bytes,
    snapshot_json_bytes,
)


class MinuteMarketDataPort(Protocol):
    async def validate_symbol(self, *, market: str, symbol: str) -> None: ...

    async def minute_bars(
        self,
        *,
        market: str,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> tuple[IntelligenceCandle, ...]: ...


class NewsDateSearchPort(Protocol):
    def search_date(
        self,
        *,
        keyword: str,
        provider_date: date,
    ) -> tuple[NewsArticleCandidate, ...]: ...


class PointInTimeMarketDataPort(Protocol):
    async def reaction_data(
        self,
        *,
        market: str,
        symbol: str,
        effective_label_anchor: datetime,
    ) -> ReactionSourceData: ...


class IdempotencyInProgressError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ChartResult:
    candles: tuple[IntelligenceCandle, ...]
    identity_checksum: str


@dataclass(frozen=True, slots=True)
class ExportSinkResult:
    sink: str
    state: str
    relative_paths: tuple[str, ...]
    artifact_checksums: tuple[str, ...]
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetResult:
    snapshot: DatasetSnapshot


@dataclass(frozen=True, slots=True)
class ExportResult:
    dataset_id: str
    sinks: tuple[ExportSinkResult, ...]


@dataclass(frozen=True, slots=True)
class ReactionResult:
    preview: ReactionPreview
    anchor_basis: str
    cohort: str


@dataclass(frozen=True, slots=True)
class NewsIntelligenceServices:
    catalog_snapshot: CatalogSnapshot
    market_data: MinuteMarketDataPort
    news_search: NewsDateSearchPort | None = None
    annotation_writer: SingleWriter | None = None
    export_root: Path | None = None
    reaction_data: PointInTimeMarketDataPort | None = None

    def search_securities(
        self, query: str, *, limit: int = 20
    ) -> tuple[CatalogSecurity, ...]:
        return search_catalog(self.catalog_snapshot, query, limit=limit)

    async def load_chart(
        self,
        *,
        market: str,
        symbol: str,
        window_start: datetime,
        window_end: datetime,
    ) -> ChartResult:
        security = next(
            (
                item
                for item in self.catalog_snapshot.securities
                if item.market == market and item.symbol == symbol
            ),
            None,
        )
        if security is None:
            raise ValueError("security is not present in the frozen catalog snapshot")
        await self.market_data.validate_symbol(market=market, symbol=symbol)
        candles = await self.market_data.minute_bars(
            market=market,
            symbol=symbol,
            window_start=window_start,
            window_end=window_end,
        )
        return ChartResult(
            candles=candles,
            identity_checksum=candle_identity_checksum(candles),
        )

    async def discover_news(
        self,
        *,
        security_id: str,
        selected_candle_at: datetime,
    ) -> NewsDiscoveryResult:
        if self.news_search is None:
            raise RuntimeError("news search service is unavailable")
        if selected_candle_at.tzinfo is None or selected_candle_at.utcoffset() is None:
            raise ValueError("selected_candle_at must be timezone-aware")
        security = self._security(security_id)

        selected_kst = selected_candle_at.astimezone(KST)
        window_start = selected_kst - timedelta(hours=1)
        available_aliases = security.terms_on(selected_kst.date())
        official = next(
            (
                alias
                for alias in available_aliases
                if alias.term.casefold() == security.display_name.casefold()
            ),
            None,
        )
        if official is None:
            raise ValueError(
                "official security name is unavailable for the selected date"
            )
        aliases = (official,) + tuple(
            alias
            for alias in sorted(
                available_aliases,
                key=lambda item: (item.term.casefold(), item.alias_id),
            )
            if alias.alias_id != official.alias_id
        )[:2]
        if not aliases:
            raise ValueError("no valid aliases exist for the selected date")
        plan = build_discovery_plan(
            window_start=window_start,
            window_end=selected_kst,
            aliases=aliases,
        )

        candidates: dict[str, tuple[NewsArticleCandidate, set[str], set[int]]] = {}
        for call in plan.calls:
            rows = await asyncio.to_thread(
                self.news_search.search_date,
                keyword=call.query,
                provider_date=call.provider_date,
            )
            for article in rows:
                published_kst = article.published_at.astimezone(KST)
                if not window_start <= published_kst <= selected_kst:
                    continue
                existing = candidates.get(article.canonical_url)
                if existing is None:
                    candidates[article.canonical_url] = (
                        article,
                        {call.alias_id},
                        {call.ordinal},
                    )
                    continue
                preferred, matched_aliases, matched_calls = existing
                matched_aliases.add(call.alias_id)
                matched_calls.add(call.ordinal)
                if _article_preference(article) > _article_preference(preferred):
                    candidates[article.canonical_url] = (
                        article,
                        matched_aliases,
                        matched_calls,
                    )

        articles = tuple(
            sorted(
                (
                    DiscoveredNewsArticle(
                        sample_id=_sample_id(
                            _article_id(url),
                            security_id,
                            article.published_at.astimezone(KST),
                        ),
                        article_id=_article_id(url),
                        title=article.title,
                        description=article.description,
                        published_at=article.published_at.astimezone(KST),
                        original_url=article.original_url,
                        naver_url=article.naver_url,
                        canonical_url=url,
                        matched_alias_ids=tuple(sorted(alias_ids)),
                        matched_call_ordinals=tuple(sorted(call_ordinals)),
                    )
                    for url, (article, alias_ids, call_ordinals) in candidates.items()
                ),
                key=lambda article: (article.published_at, article.canonical_url),
            )
        )
        result = NewsDiscoveryResult(
            security_id=security_id,
            selected_candle_at=selected_kst,
            plan=plan,
            executed_call_count=plan.expected_call_count,
            complete=True,
            articles=articles,
        )
        if self.annotation_writer is not None and articles:
            created_at = datetime.now(timezone.utc)
            security_provenance = {
                "catalog_snapshot_id": self.catalog_snapshot.snapshot_id,
                "catalog_version": self.catalog_snapshot.version,
                "catalog_checksum": self.catalog_snapshot.checksum,
                "selected_candle_at": selected_kst.isoformat(),
                "discovery_plan": {
                    "version": plan.version,
                    "window_start": plan.window_start.isoformat(),
                    "window_end": plan.window_end.isoformat(),
                    "offset_min_minutes": plan.offset_min_minutes,
                    "offset_max_minutes": plan.offset_max_minutes,
                    "expected_call_count": plan.expected_call_count,
                    "calls": [
                        {
                            "ordinal": call.ordinal,
                            "alias_id": call.alias_id,
                            "query": call.query,
                            "provider_date": call.provider_date.isoformat(),
                        }
                        for call in plan.calls
                    ],
                },
            }

            def persist(connection):
                for article in articles:
                    calls = [
                        {
                            "ordinal": call.ordinal,
                            "alias_id": call.alias_id,
                            "query": call.query,
                            "provider_date": call.provider_date.isoformat(),
                        }
                        for call in plan.calls
                        if call.ordinal in article.matched_call_ordinals
                    ]
                    upsert_sample(
                        connection,
                        sample=SampleRecord(
                            sample_id=article.sample_id,
                            article_id=article.article_id,
                            security_id=security_id,
                            market=security.market,
                            symbol=security.symbol,
                            title=article.title,
                            description=article.description,
                            published_at=article.published_at,
                            effective_label_anchor=article.published_at,
                            anchor_basis="published_at_proxy",
                            cohort="historical_publication_proxy",
                            provenance_json=json.dumps(
                                {
                                    **security_provenance,
                                    "matched_call_ordinals": list(
                                        article.matched_call_ordinals
                                    ),
                                    "contributing_calls": calls,
                                },
                                ensure_ascii=False,
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                            reaction_class=None,
                            reaction_exclusion_reason="benchmark_unavailable",
                        ),
                        created_at=created_at,
                    )

            await asyncio.to_thread(self.annotation_writer.execute, persist)
        return result

    def suggest_relevance(
        self,
        *,
        security_id: str,
        title: str,
        description: str,
        selected_on: date,
    ) -> RelevanceSuggestion:
        security = self._security(security_id)
        aliases = security.terms_on(selected_on)
        if not aliases:
            raise ValueError("no valid aliases exist for the selected date")
        return suggest_direct_mention(
            title=title,
            description=description,
            aliases=aliases,
        )

    async def preview_reaction_for_sample(self, *, sample_id: str) -> ReactionResult:
        if self.annotation_writer is None:
            raise RuntimeError("dataset writer is unavailable")
        sample = await asyncio.to_thread(
            self.annotation_writer.read,
            lambda connection: load_sample(connection, sample_id=sample_id),
        )
        if sample is None:
            raise ValueError("sample is not a persisted discovery result")
        if self.reaction_data is None:
            return ReactionResult(
                preview=preview_reaction(
                    effective_label_anchor=sample.effective_label_anchor,
                    stock_points=(),
                    benchmark_points=None,
                    session_minutes=(sample.effective_label_anchor,),
                ),
                anchor_basis=sample.anchor_basis,
                cohort=sample.cohort,
            )
        data = await self.reaction_data.reaction_data(
            market=sample.market,
            symbol=sample.symbol,
            effective_label_anchor=sample.effective_label_anchor,
        )
        if data.benchmark_proof != approved_kiwoom_benchmark(sample.market):
            raise ValueError("benchmark ownership proof does not match security market")
        if not data.session_id or not data.source_checksum:
            raise ValueError("reaction source provenance is incomplete")
        result = preview_reaction(
            effective_label_anchor=sample.effective_label_anchor,
            stock_points=data.stock_points,
            benchmark_points=data.benchmark_points,
            session_minutes=data.session_minutes,
        )
        provenance = json.loads(sample.provenance_json)
        provenance["reaction"] = {
            "benchmark": data.benchmark_proof.benchmark_name,
            "benchmark_code": data.benchmark_proof.benchmark_code,
            "api_id": data.benchmark_proof.api_id,
            "source_version": data.benchmark_proof.source_version,
            "session_id": data.session_id,
            "source_checksum": data.source_checksum,
            "label_version": result.label_version,
        }
        updated = replace(
            sample,
            provenance_json=json.dumps(
                provenance, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
            reaction_class=result.reaction_class,
            reaction_exclusion_reason=result.exclusion_reason,
        )
        await asyncio.to_thread(
            self.annotation_writer.execute,
            lambda connection: upsert_sample(
                connection,
                sample=updated,
                created_at=datetime.now(timezone.utc),
            ),
        )
        return ReactionResult(
            preview=result,
            anchor_basis=sample.anchor_basis,
            cohort=sample.cohort,
        )

    async def save_annotation(
        self,
        *,
        idempotency_key: str,
        sample_id: str,
        final_value: str,
        actor: str,
        note: str | None,
        now: datetime | None = None,
        annotation_id: str | None = None,
    ) -> AnnotationRevisionRecord:
        if self.annotation_writer is None:
            raise RuntimeError("annotation writer is unavailable")
        if final_value not in {"relevant", "not_relevant", "uncertain"}:
            raise ValueError("unsupported final relevance value")
        sample = await asyncio.to_thread(
            self.annotation_writer.read,
            lambda connection: load_sample(connection, sample_id=sample_id),
        )
        if sample is None:
            raise ValueError("sample is not a persisted discovery result")
        suggestion = self.suggest_relevance(
            security_id=sample.security_id,
            title=sample.title,
            description=sample.description,
            selected_on=sample.published_at.astimezone(KST).date(),
        )
        evidence_json = json.dumps(
            [
                {
                    "alias_id": item.alias_id,
                    "term": item.term,
                    "field": item.field,
                    "start": item.start,
                    "end": item.end,
                    "matched_text": item.matched_text,
                }
                for item in suggestion.evidence
            ],
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        created_at = now or datetime.now(timezone.utc)
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        payload = {
            "sample_id": sample_id,
            "final_value": final_value,
            "actor": actor,
            "note": note,
            "suggestion_value": suggestion.value,
            "evidence_json": evidence_json,
            "rule_version": suggestion.rule_version,
        }
        owner_id = uuid.uuid4().hex
        claim = await asyncio.to_thread(
            self.annotation_writer.execute,
            lambda connection: claim_operation(
                connection,
                operation="annotation.create",
                idempotency_key=idempotency_key,
                request_hash=canonical_request_hash(payload),
                owner_id=owner_id,
                now=created_at,
                lease_duration=timedelta(minutes=5),
                manage_transaction=False,
            ),
        )
        if claim.disposition is ClaimDisposition.IN_PROGRESS:
            raise IdempotencyInProgressError(
                "annotation request is already in progress"
            )
        if claim.disposition is ClaimDisposition.REPLAY:
            history = await self.annotation_history(sample_id=sample_id)
            replay = next(
                (item for item in history if item.annotation_id == claim.result_ref),
                None,
            )
            if replay is None:
                raise IdempotencyConflictError("annotation replay target is missing")
            return replay

        result_id = annotation_id or uuid.uuid4().hex

        def mutation(connection):
            revision = append_annotation_revision(
                connection,
                annotation_id=result_id,
                sample_id=sample.sample_id,
                article_id=sample.article_id,
                security_id=sample.security_id,
                final_value=final_value,
                suggestion_value=suggestion.value,
                evidence_json=evidence_json,
                rule_version=suggestion.rule_version,
                actor=actor,
                note=note,
                created_at=created_at,
            )
            mark_operation_succeeded(
                connection,
                operation="annotation.create",
                idempotency_key=idempotency_key,
                owner_id=owner_id,
                result_ref=result_id,
                now=created_at,
            )
            return revision

        try:
            return await asyncio.to_thread(self.annotation_writer.execute, mutation)
        except Exception:
            await asyncio.to_thread(
                self.annotation_writer.execute,
                lambda connection: mark_operation_rolled_back(
                    connection,
                    operation="annotation.create",
                    idempotency_key=idempotency_key,
                    owner_id=owner_id,
                    error_code="annotation_write_failed",
                    now=created_at,
                ),
            )
            raise

    async def annotation_history(
        self,
        *,
        sample_id: str,
    ) -> tuple[AnnotationRevisionRecord, ...]:
        if self.annotation_writer is None:
            raise RuntimeError("annotation writer is unavailable")
        return await asyncio.to_thread(
            self.annotation_writer.read,
            lambda connection: list_annotation_revisions(
                connection,
                sample_id=sample_id,
            ),
        )

    async def freeze_dataset(
        self,
        *,
        idempotency_key: str,
        dataset_id: str,
        purpose: str,
        cohort: str,
        annotation_ids: tuple[str, ...],
        now: datetime | None = None,
    ) -> DatasetResult:
        if self.annotation_writer is None:
            raise RuntimeError("dataset writer is unavailable")
        if not annotation_ids or len(set(annotation_ids)) != len(annotation_ids):
            raise ValueError("annotation revision IDs must be non-empty and unique")
        candidates = await asyncio.to_thread(
            self.annotation_writer.read,
            lambda connection: load_authoritative_candidates(
                connection,
                annotation_ids=annotation_ids,
            ),
        )
        snapshot = build_dataset_snapshot(
            dataset_id=dataset_id,
            purpose=purpose,
            cohort=cohort,
            candidates=candidates,
        )
        created_at = now or datetime.now(timezone.utc)
        owner_id = uuid.uuid4().hex
        request_hash = canonical_request_hash(
            {
                "dataset_id": dataset_id,
                "purpose": purpose,
                "cohort": cohort,
                "annotation_ids": sorted(annotation_ids),
            }
        )
        claim = await asyncio.to_thread(
            self.annotation_writer.execute,
            lambda connection: claim_operation(
                connection,
                operation="dataset.freeze",
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                owner_id=owner_id,
                now=created_at,
                lease_duration=timedelta(minutes=5),
                manage_transaction=False,
            ),
        )
        if claim.disposition is ClaimDisposition.IN_PROGRESS:
            raise IdempotencyInProgressError("dataset request is already in progress")
        if claim.disposition is ClaimDisposition.REPLAY:
            payload = await asyncio.to_thread(
                self.annotation_writer.read,
                lambda connection: load_dataset_payload(
                    connection,
                    dataset_id=claim.result_ref or dataset_id,
                ),
            )
            if payload is None:
                raise IdempotencyConflictError("dataset replay target is missing")
            snapshot = _snapshot_from_payload(payload)
        else:
            payload = snapshot_json_bytes(snapshot).decode("utf-8")

            def mutation(connection):
                persist_dataset_snapshot(
                    connection,
                    dataset_id=dataset_id,
                    purpose=purpose,
                    cohort=cohort,
                    snapshot_checksum=snapshot.snapshot_checksum,
                    manifest_json=payload,
                    members=tuple(dict(member) for member in snapshot.members),
                    created_at=created_at,
                )
                mark_operation_succeeded(
                    connection,
                    operation="dataset.freeze",
                    idempotency_key=idempotency_key,
                    owner_id=owner_id,
                    result_ref=dataset_id,
                    now=created_at,
                )

            try:
                await asyncio.to_thread(self.annotation_writer.execute, mutation)
            except Exception:
                await asyncio.to_thread(
                    self.annotation_writer.execute,
                    lambda connection: mark_operation_rolled_back(
                        connection,
                        operation="dataset.freeze",
                        idempotency_key=idempotency_key,
                        owner_id=owner_id,
                        error_code="dataset_freeze_failed",
                        now=datetime.now(timezone.utc),
                    ),
                )
                raise

        return DatasetResult(snapshot=snapshot)

    async def export_dataset(
        self,
        *,
        idempotency_key: str,
        dataset_id: str,
        sinks: tuple[str, ...],
        now: datetime | None = None,
    ) -> ExportResult:
        if self.annotation_writer is None:
            raise RuntimeError("dataset writer is unavailable")
        unsupported = set(sinks) - {"db", "json", "csv"}
        if unsupported or not sinks or len(set(sinks)) != len(sinks):
            raise ValueError("select unique supported export sinks")
        sinks = tuple(sorted(sinks))
        payload = await asyncio.to_thread(
            self.annotation_writer.read,
            lambda connection: load_dataset_payload(connection, dataset_id=dataset_id),
        )
        if payload is None:
            raise ValueError("dataset does not exist")
        snapshot = _snapshot_from_payload(payload)
        artifacts = self._export_artifacts(snapshot, sinks)
        created_at = now or datetime.now(timezone.utc)
        owner_id = uuid.uuid4().hex
        export_request = {
            "dataset_id": dataset_id,
            "sinks": list(sinks),
            "artifacts": [
                {"sink": sink, "path": path, "checksum": _content_checksum(content)}
                for sink, path, content in artifacts
            ],
        }
        claim = await asyncio.to_thread(
            self.annotation_writer.execute,
            lambda connection: claim_operation(
                connection,
                operation="dataset.export",
                idempotency_key=idempotency_key,
                request_hash=canonical_request_hash(export_request),
                owner_id=owner_id,
                now=created_at,
                lease_duration=timedelta(seconds=1),
                manage_transaction=False,
            ),
        )
        if claim.disposition is ClaimDisposition.IN_PROGRESS:
            raise IdempotencyInProgressError("export request is already in progress")
        if claim.disposition is ClaimDisposition.REPLAY:
            return await self.export_status(dataset_id=dataset_id)

        for sink, path, content in artifacts:
            expected_checksum = _content_checksum(content)
            export_id = hashlib.sha256(
                f"{dataset_id}\0{sink}\0{path}".encode("utf-8")
            ).hexdigest()
            record = await asyncio.to_thread(
                self.annotation_writer.execute,
                lambda connection, export_id=export_id, sink=sink, path=path, expected_checksum=expected_checksum: (
                    claim_export_artifact(
                        connection,
                        export_id=export_id,
                        dataset_id=dataset_id,
                        sink=sink,
                        expected_path=path,
                        expected_checksum=expected_checksum,
                        now=created_at,
                    )
                ),
            )
            export_id = record.export_id
            if record.state == "succeeded":
                continue
            try:
                if sink != "db":
                    if self.export_root is None:
                        raise RuntimeError("export_root_unavailable")
                    _, artifact_checksum, _ = await asyncio.to_thread(
                        write_or_reconcile,
                        root=self.export_root,
                        relative_path=path,
                        content=content,
                    )
                else:
                    artifact_checksum = expected_checksum
                await asyncio.to_thread(
                    self.annotation_writer.execute,
                    lambda connection, export_id=export_id, artifact_checksum=artifact_checksum: (
                        finish_export_artifact(
                            connection,
                            export_id=export_id,
                            artifact_checksum=artifact_checksum,
                            error_code=None,
                            now=created_at,
                        )
                    ),
                )
            except Exception as error:
                error_code = (
                    "artifact_checksum_conflict"
                    if isinstance(error, ExportArtifactConflictError)
                    else "export_root_unavailable"
                    if str(error) == "export_root_unavailable"
                    else "export_failed"
                )
                await asyncio.to_thread(
                    self.annotation_writer.execute,
                    lambda connection, export_id=export_id, error_code=error_code: (
                        finish_export_artifact(
                            connection,
                            export_id=export_id,
                            artifact_checksum=None,
                            error_code=error_code,
                            now=created_at,
                        )
                    ),
                )
        await asyncio.to_thread(
            self.annotation_writer.execute,
            lambda connection: mark_operation_succeeded(
                connection,
                operation="dataset.export",
                idempotency_key=idempotency_key,
                owner_id=owner_id,
                result_ref=dataset_id,
                now=created_at,
            ),
        )
        return await self.export_status(dataset_id=dataset_id)

    async def export_status(self, *, dataset_id: str) -> ExportResult:
        if self.annotation_writer is None:
            raise RuntimeError("dataset writer is unavailable")
        records = await asyncio.to_thread(
            self.annotation_writer.read,
            lambda connection: list_exports(connection, dataset_id=dataset_id),
        )
        grouped: dict[str, list[Any]] = {}
        for record in records:
            grouped.setdefault(record.sink, []).append(record)
        sinks = tuple(
            ExportSinkResult(
                sink=sink,
                state=(
                    "failed"
                    if any(item.state == "failed" for item in items)
                    else "pending"
                    if any(item.state == "pending" for item in items)
                    else "succeeded"
                ),
                relative_paths=tuple(item.expected_path for item in items),
                artifact_checksums=tuple(
                    item.artifact_checksum for item in items if item.artifact_checksum
                ),
                error_code=next(
                    (item.error_code for item in items if item.error_code), None
                ),
            )
            for sink, items in sorted(grouped.items())
        )
        return ExportResult(dataset_id=dataset_id, sinks=sinks)

    def _export_artifacts(
        self, snapshot: DatasetSnapshot, sinks: tuple[str, ...]
    ) -> tuple[tuple[str, str, bytes], ...]:
        result: list[tuple[str, str, bytes]] = []
        if "db" in sinks:
            result.append(
                (
                    "db",
                    f"postgres://datasets/{snapshot.dataset_id}",
                    snapshot.snapshot_checksum.encode(),
                )
            )
        if "json" in sinks:
            result.append(
                (
                    "json",
                    f"{snapshot.dataset_id}/{snapshot.dataset_id}.json",
                    snapshot_json_bytes(snapshot),
                )
            )
        if "csv" in sinks:
            result.append(
                (
                    "csv",
                    f"{snapshot.dataset_id}/{snapshot.dataset_id}.csv",
                    snapshot_csv_bytes(snapshot),
                )
            )
            manifest = (
                json.dumps(
                    {"manifest": snapshot.manifest, "exclusions": snapshot.exclusions},
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
                + b"\n"
            )
            result.append(
                (
                    "csv",
                    f"{snapshot.dataset_id}/{snapshot.dataset_id}.manifest.json",
                    manifest,
                )
            )
        return tuple(result)

    def _security(self, security_id: str) -> CatalogSecurity:
        security = next(
            (
                item
                for item in self.catalog_snapshot.securities
                if item.security_id == security_id
            ),
            None,
        )
        if security is None:
            raise ValueError("security is not present in the frozen catalog snapshot")
        return security


def _article_preference(article: NewsArticleCandidate) -> tuple[float, str, str, str]:
    return (
        article.published_at.timestamp(),
        article.title,
        article.description,
        article.naver_url,
    )


def _article_id(canonical_url: str) -> str:
    return hashlib.sha256(canonical_url.encode("utf-8")).hexdigest()


def _sample_id(
    article_id: str, security_id: str, effective_label_anchor: datetime
) -> str:
    identity = f"{article_id}\0{security_id}\0{effective_label_anchor.isoformat()}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _content_checksum(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _snapshot_from_payload(payload: str) -> DatasetSnapshot:
    decoded = json.loads(payload)
    manifest = decoded["manifest"]
    return DatasetSnapshot(
        dataset_id=manifest["dataset_id"],
        purpose=manifest["purpose"],
        cohort=manifest["cohort"],
        snapshot_checksum=manifest["snapshot_checksum"],
        manifest=manifest,
        members=tuple(decoded["members"]),
        exclusions=tuple(decoded["exclusions"]),
    )
