"""Application factory kept free of provider credentials and construction."""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from modules.domain.news_intelligence import (
    MarketDataProviderError,
    NewsDiscoveryIncompleteError,
    NewsProviderError,
)
from modules.orchestration.news_intelligence import (
    IdempotencyInProgressError,
    NewsIntelligenceServices,
)
from modules.storage.news_intelligence.repositories import (
    AnnotationRevisionRecord,
    IdempotencyConflictError,
)


class HealthResponse(BaseModel):
    status: str


class CatalogItemResponse(BaseModel):
    security_id: str
    market: str
    symbol: str
    display_name: str
    alias_terms: list[str]
    catalog_snapshot_id: str
    catalog_source: str
    catalog_acquired_at: datetime
    catalog_checksum: str
    catalog_stale: bool
    historical_name_status: str = "current_only"


class CandleResponse(BaseModel):
    timestamp: datetime
    open: str
    high: str
    low: str
    close: str
    volume: int
    turnover: str


class ChartResponse(BaseModel):
    market: str
    symbol: str
    interval: str = "1min"
    identity_checksum: str
    replayable: bool = False
    candles: list[CandleResponse]


class DiscoverNewsRequest(BaseModel):
    security_id: str
    selected_candle_at: datetime
    window_start: datetime | None = None


class DiscoveryPlanCallResponse(BaseModel):
    ordinal: int
    alias_id: str
    query: str
    provider_date: str


class DiscoveredArticleResponse(BaseModel):
    sample_id: str
    article_id: str
    title: str
    description: str
    published_at: datetime
    original_url: str | None
    naver_url: str | None
    canonical_url: str
    matched_alias_ids: list[str]
    matched_call_ordinals: list[int]
    source: str


class DiscoverNewsResponse(BaseModel):
    security_id: str
    selected_candle_at: datetime
    window_start: datetime
    window_end: datetime
    plan_version: str
    expected_call_count: int
    executed_call_count: int
    complete: bool
    calls: list[DiscoveryPlanCallResponse]
    articles: list[DiscoveredArticleResponse]


class RelevanceSuggestionRequest(BaseModel):
    security_id: str
    title: str
    description: str
    selected_on: date


class DirectMentionEvidenceResponse(BaseModel):
    alias_id: str
    term: str
    field: str
    start: int
    end: int
    matched_text: str


class RelevanceSuggestionResponse(BaseModel):
    value: str
    rule_version: str
    evidence: list[DirectMentionEvidenceResponse]


class AnnotationRequest(BaseModel):
    sample_id: str
    final_value: str
    actor: str
    note: str | None = None


class AnnotationRevisionResponse(BaseModel):
    annotation_id: str
    sample_id: str
    article_id: str
    security_id: str
    revision: int
    previous_annotation_id: str | None
    final_value: str
    suggestion_value: str
    evidence: list[dict[str, object]]
    rule_version: str
    actor: str
    note: str | None
    created_at: datetime


class ReactionPreviewRequest(BaseModel):
    sample_id: str


class ReactionPreviewResponse(BaseModel):
    effective_label_anchor: datetime
    anchor_basis: str
    cohort: str
    feature_cutoff_at: datetime
    label_window_end: datetime | None
    stock_return: str | None
    benchmark_return: str | None
    abnormal_return: str | None
    turnover_zscore: str | None
    reaction_class: str | None
    is_strong_reaction: bool | None
    exclusion_reason: str | None
    label_version: str


class FreezeDatasetRequest(BaseModel):
    dataset_id: str
    purpose: str
    cohort: str
    annotation_ids: list[str]


class ExportSinkResponse(BaseModel):
    sink: str
    state: str
    relative_paths: list[str]
    artifact_checksums: list[str]
    error_code: str | None


class FreezeDatasetResponse(BaseModel):
    dataset_id: str
    purpose: str
    cohort: str
    snapshot_checksum: str
    manifest: dict[str, object]
    members: list[dict[str, object]]
    exclusions: list[dict[str, object]]


class ExportDatasetRequest(BaseModel):
    sinks: list[str]


class ExportDatasetResponse(BaseModel):
    dataset_id: str
    sinks: list[ExportSinkResponse]


app = FastAPI(
    title="FinLabs News Intelligence API",
    version="0.1.0",
    description="Local-first collection and labeling API.",
)


@app.exception_handler(HTTPException)
async def safe_http_error(_: Request, error: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={
            "code": f"http_{error.status_code}",
            "message": str(error.detail),
            "retryable": error.status_code in {429, 502, 503},
            "details_safe": None,
            "correlation_id": uuid.uuid4().hex,
        },
    )


@app.exception_handler(RequestValidationError)
async def safe_validation_error(
    _: Request, error: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "request_validation_failed",
            "message": "request validation failed",
            "retryable": False,
            "details_safe": {"error_count": len(error.errors())},
            "correlation_id": uuid.uuid4().hex,
        },
    )


@app.get("/api/health", operation_id="getHealth", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


def get_services(request: Request) -> NewsIntelligenceServices:
    services = getattr(request.app.state, "news_intelligence_services", None)
    if services is None:
        raise HTTPException(
            status_code=503, detail="news intelligence services unavailable"
        )
    return services


Services = Annotated[NewsIntelligenceServices, Depends(get_services)]


@app.get(
    "/api/catalog",
    operation_id="searchCatalog",
    response_model=list[CatalogItemResponse],
)
def catalog_search(
    services: Services,
    q: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[CatalogItemResponse]:
    return [
        CatalogItemResponse(
            security_id=item.security_id,
            market=item.market,
            symbol=item.symbol,
            display_name=item.display_name,
            alias_terms=[alias.term for alias in item.aliases],
            catalog_snapshot_id=services.catalog_snapshot.snapshot_id,
            catalog_source=services.catalog_snapshot.source,
            catalog_acquired_at=services.catalog_snapshot.acquired_at,
            catalog_checksum=services.catalog_snapshot.checksum,
            catalog_stale=services.catalog_snapshot.is_stale(
                now=datetime.now(services.catalog_snapshot.acquired_at.tzinfo),
                max_age=timedelta(days=7),
            ),
        )
        for item in services.search_securities(q, limit=limit)
    ]


@app.get(
    "/api/charts/{symbol}",
    operation_id="loadChart",
    response_model=ChartResponse,
)
async def chart_load(
    symbol: str,
    services: Services,
    market: str = Query(pattern="^(KOSPI|KOSDAQ)$"),
    start_at: datetime = Query(),
    end_at: datetime = Query(),
    chart_type: str = Query(default="minute", pattern="^(minute|daily)$"),
    interval_minutes: int = Query(default=1),
) -> ChartResponse:
    try:
        result = await services.load_chart(
            market=market,
            symbol=symbol,
            window_start=start_at,
            window_end=end_at,
            chart_type=chart_type,
            interval_minutes=interval_minutes,
        )
    except MarketDataProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    interval = "1d" if chart_type == "daily" else f"{interval_minutes}min"
    return ChartResponse(
        market=market,
        symbol=symbol,
        interval=interval,
        identity_checksum=result.identity_checksum,
        candles=[
            CandleResponse(
                timestamp=candle.timestamp,
                open=str(candle.open),
                high=str(candle.high),
                low=str(candle.low),
                close=str(candle.close),
                volume=candle.volume,
                turnover=str(candle.turnover),
            )
            for candle in result.candles
        ],
    )


@app.post(
    "/api/news/discover",
    operation_id="discoverNews",
    response_model=DiscoverNewsResponse,
)
async def discover_news(
    command: DiscoverNewsRequest,
    services: Services,
) -> DiscoverNewsResponse:
    try:
        result = await services.discover_news(
            security_id=command.security_id,
            selected_candle_at=command.selected_candle_at,
            window_start=command.window_start,
        )
    except NewsDiscoveryIncompleteError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except NewsProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return DiscoverNewsResponse(
        security_id=result.security_id,
        selected_candle_at=result.selected_candle_at,
        window_start=result.plan.window_start,
        window_end=result.plan.window_end,
        plan_version=result.plan.version,
        expected_call_count=result.plan.expected_call_count,
        executed_call_count=result.executed_call_count,
        complete=result.complete,
        calls=[
            DiscoveryPlanCallResponse(
                ordinal=call.ordinal,
                alias_id=call.alias_id,
                query=call.query,
                provider_date=call.provider_date.isoformat(),
            )
            for call in result.plan.calls
        ],
        articles=[
            DiscoveredArticleResponse(
                sample_id=article.sample_id,
                article_id=article.article_id,
                title=article.title,
                description=article.description,
                published_at=article.published_at,
                original_url=article.original_url,
                naver_url=article.naver_url,
                canonical_url=article.canonical_url,
                matched_alias_ids=list(article.matched_alias_ids),
                matched_call_ordinals=list(article.matched_call_ordinals),
                source=article.source,
            )
            for article in result.articles
        ],
    )


@app.post(
    "/api/relevance/suggest",
    operation_id="suggestRelevance",
    response_model=RelevanceSuggestionResponse,
)
def suggest_relevance(
    command: RelevanceSuggestionRequest,
    services: Services,
) -> RelevanceSuggestionResponse:
    try:
        suggestion = services.suggest_relevance(
            security_id=command.security_id,
            title=command.title,
            description=command.description,
            selected_on=command.selected_on,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RelevanceSuggestionResponse(
        value=suggestion.value,
        rule_version=suggestion.rule_version,
        evidence=[
            DirectMentionEvidenceResponse(
                alias_id=item.alias_id,
                term=item.term,
                field=item.field,
                start=item.start,
                end=item.end,
                matched_text=item.matched_text,
            )
            for item in suggestion.evidence
        ],
    )


@app.post(
    "/api/annotations",
    operation_id="createAnnotation",
    response_model=AnnotationRevisionResponse,
)
async def create_annotation(
    command: AnnotationRequest,
    services: Services,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> AnnotationRevisionResponse:
    try:
        revision = await services.save_annotation(
            idempotency_key=idempotency_key,
            sample_id=command.sample_id,
            final_value=command.final_value,
            actor=command.actor,
            note=command.note,
        )
    except (IdempotencyConflictError, IdempotencyInProgressError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _annotation_response(revision)


@app.get(
    "/api/annotations/{sample_id}",
    operation_id="getAnnotationHistory",
    response_model=list[AnnotationRevisionResponse],
)
async def annotation_history(
    sample_id: str,
    services: Services,
) -> list[AnnotationRevisionResponse]:
    try:
        revisions = await services.annotation_history(sample_id=sample_id)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return [_annotation_response(revision) for revision in revisions]


def _annotation_response(
    revision: AnnotationRevisionRecord,
) -> AnnotationRevisionResponse:
    return AnnotationRevisionResponse(
        annotation_id=revision.annotation_id,
        sample_id=revision.sample_id,
        article_id=revision.article_id,
        security_id=revision.security_id,
        revision=revision.revision,
        previous_annotation_id=revision.previous_annotation_id,
        final_value=revision.final_value,
        suggestion_value=revision.suggestion_value,
        evidence=json.loads(revision.evidence_json),
        rule_version=revision.rule_version,
        actor=revision.actor,
        note=revision.note,
        created_at=revision.created_at,
    )


@app.post(
    "/api/datasets/preview",
    operation_id="previewReaction",
    response_model=ReactionPreviewResponse,
)
async def preview_reaction_route(
    command: ReactionPreviewRequest,
    services: Services,
) -> ReactionPreviewResponse:
    try:
        result = await services.preview_reaction_for_sample(sample_id=command.sample_id)
    except MarketDataProviderError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    preview = result.preview
    return ReactionPreviewResponse(
        effective_label_anchor=preview.effective_label_anchor,
        anchor_basis=result.anchor_basis,
        cohort=result.cohort,
        feature_cutoff_at=preview.feature_cutoff_at,
        label_window_end=preview.label_window_end,
        stock_return=_decimal_text(preview.stock_return),
        benchmark_return=_decimal_text(preview.benchmark_return),
        abnormal_return=_decimal_text(preview.abnormal_return),
        turnover_zscore=_decimal_text(preview.turnover_zscore),
        reaction_class=preview.reaction_class,
        is_strong_reaction=preview.is_strong_reaction,
        exclusion_reason=preview.exclusion_reason,
        label_version=preview.label_version,
    )


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


@app.post(
    "/api/datasets",
    operation_id="freezeDataset",
    response_model=FreezeDatasetResponse,
)
async def freeze_dataset_route(
    command: FreezeDatasetRequest,
    services: Services,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> FreezeDatasetResponse:
    try:
        result = await services.freeze_dataset(
            idempotency_key=idempotency_key,
            dataset_id=command.dataset_id,
            purpose=command.purpose,
            cohort=command.cohort,
            annotation_ids=tuple(command.annotation_ids),
        )
    except (IdempotencyConflictError, IdempotencyInProgressError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return FreezeDatasetResponse(
        dataset_id=result.snapshot.dataset_id,
        purpose=result.snapshot.purpose,
        cohort=result.snapshot.cohort,
        snapshot_checksum=result.snapshot.snapshot_checksum,
        manifest=dict(result.snapshot.manifest),
        members=[dict(member) for member in result.snapshot.members],
        exclusions=[dict(item) for item in result.snapshot.exclusions],
    )


@app.post(
    "/api/datasets/{dataset_id}/exports",
    operation_id="exportDataset",
    response_model=ExportDatasetResponse,
)
async def export_dataset_route(
    dataset_id: str,
    command: ExportDatasetRequest,
    services: Services,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> ExportDatasetResponse:
    return await _run_export(
        services=services,
        idempotency_key=idempotency_key,
        dataset_id=dataset_id,
        sinks=tuple(command.sinks),
    )


@app.get(
    "/api/datasets/{dataset_id}/exports",
    operation_id="getDatasetExports",
    response_model=ExportDatasetResponse,
)
async def export_status_route(
    dataset_id: str, services: Services
) -> ExportDatasetResponse:
    result = await services.export_status(dataset_id=dataset_id)
    return _export_response(result.dataset_id, result.sinks)


@app.post(
    "/api/datasets/{dataset_id}/exports/{sink}/retry",
    operation_id="retryDatasetExport",
    response_model=ExportDatasetResponse,
)
async def retry_export_route(
    dataset_id: str,
    sink: str,
    services: Services,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=200
    ),
) -> ExportDatasetResponse:
    return await _run_export(
        services=services,
        idempotency_key=idempotency_key,
        dataset_id=dataset_id,
        sinks=(sink,),
    )


async def _run_export(
    *,
    services: NewsIntelligenceServices,
    idempotency_key: str,
    dataset_id: str,
    sinks: tuple[str, ...],
) -> ExportDatasetResponse:
    try:
        result = await services.export_dataset(
            idempotency_key=idempotency_key,
            dataset_id=dataset_id,
            sinks=sinks,
        )
    except (IdempotencyConflictError, IdempotencyInProgressError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return _export_response(result.dataset_id, result.sinks)


def _export_response(dataset_id: str, sinks: tuple) -> ExportDatasetResponse:
    return ExportDatasetResponse(
        dataset_id=dataset_id,
        sinks=[
            ExportSinkResponse(
                sink=item.sink,
                state=item.state,
                relative_paths=list(item.relative_paths),
                artifact_checksums=list(item.artifact_checksums),
                error_code=item.error_code,
            )
            for item in sinks
        ],
    )
