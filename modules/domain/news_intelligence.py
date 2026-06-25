"""Pure contracts for the news-intelligence data collection workflow."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
NAVER_OFFSET_MIN = timedelta(hours=-12)
NAVER_OFFSET_MAX = timedelta(hours=14)


class NewsDiscoveryIncompleteError(RuntimeError):
    """The provider could not prove that a planned search was complete."""


class NewsProviderError(RuntimeError):
    """The news provider failed before a complete result could be produced."""


class MarketDataProviderError(RuntimeError):
    """A market-data provider failed without exposing provider internals."""


class HistoricalNameStatus(StrEnum):
    CURRENT_ONLY = "current_only"
    VALIDITY_RANGED = "validity_ranged"


class TimeBasis(StrEnum):
    FIRST_SEEN_AT = "first_seen_at"
    PUBLISHED_AT_PROXY = "published_at_proxy"


class DatasetCohort(StrEnum):
    LIVE_FIRST_SEEN = "live_first_seen"
    HISTORICAL_PUBLICATION_PROXY = "historical_publication_proxy"


class DatasetPurpose(StrEnum):
    RELEVANCE_TRAINING = "relevance_training"
    REACTION_TRAINING = "reaction_training"
    COMBINED = "combined"


@dataclass(frozen=True, slots=True)
class ObservationTime:
    first_seen_at: datetime
    t0: datetime | None
    proxy_event_time: datetime | None
    effective_label_anchor: datetime
    anchor_basis: TimeBasis
    cohort: DatasetCohort

    def __post_init__(self) -> None:
        for field, value in (
            ("first_seen_at", self.first_seen_at),
            ("effective_label_anchor", self.effective_label_anchor),
        ):
            _require_aware(value, field)
        for field, value in (
            ("t0", self.t0),
            ("proxy_event_time", self.proxy_event_time),
        ):
            if value is not None:
                _require_aware(value, field)

        if self.cohort is DatasetCohort.LIVE_FIRST_SEEN:
            if self.t0 != self.first_seen_at or self.proxy_event_time is not None:
                raise ValueError("live cohort requires immutable t0=first_seen_at only")
            if (
                self.anchor_basis is not TimeBasis.FIRST_SEEN_AT
                or self.effective_label_anchor != self.t0
            ):
                raise ValueError("live effective anchor must use canonical t0")
        elif self.cohort is DatasetCohort.HISTORICAL_PUBLICATION_PROXY:
            if self.t0 is not None or self.proxy_event_time is None:
                raise ValueError(
                    "historical cohort requires proxy time and no canonical t0"
                )
            if (
                self.anchor_basis is not TimeBasis.PUBLISHED_AT_PROXY
                or self.effective_label_anchor != self.proxy_event_time
            ):
                raise ValueError("historical effective anchor must use proxy time")


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    kind: str
    ref_id: str
    version: str
    checksum: str


@dataclass(frozen=True, slots=True)
class CatalogAlias:
    alias_id: str
    term: str
    valid_from: date
    valid_to: date | None
    source: str
    historical_name_status: HistoricalNameStatus

    def is_valid_on(self, selected_on: date) -> bool:
        return self.valid_from <= selected_on and (
            self.valid_to is None or selected_on <= self.valid_to
        )


@dataclass(frozen=True, slots=True)
class CatalogSecurity:
    security_id: str
    market: str
    symbol: str
    display_name: str
    aliases: tuple[CatalogAlias, ...]

    def terms_on(self, selected_on: date) -> tuple[CatalogAlias, ...]:
        return tuple(alias for alias in self.aliases if alias.is_valid_on(selected_on))


@dataclass(frozen=True, slots=True)
class CatalogSnapshot:
    snapshot_id: str
    version: str
    source: str
    acquired_at: datetime
    checksum: str
    securities: tuple[CatalogSecurity, ...]

    def __post_init__(self) -> None:
        _require_aware(self.acquired_at, "acquired_at")

    def is_stale(self, *, now: datetime, max_age: timedelta) -> bool:
        _require_aware(now, "now")
        return now - self.acquired_at > max_age


@dataclass(frozen=True, slots=True)
class DiscoveryCall:
    ordinal: int
    alias_id: str
    query: str
    provider_date: date


@dataclass(frozen=True, slots=True)
class DiscoveryPlan:
    version: str
    window_start: datetime
    window_end: datetime
    offset_min_minutes: int
    offset_max_minutes: int
    calls: tuple[DiscoveryCall, ...]

    @property
    def expected_call_count(self) -> int:
        return len(self.calls)


@dataclass(frozen=True, slots=True)
class IntelligenceCandle:
    market: str
    symbol: str
    interval: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    turnover: Decimal

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")


@dataclass(frozen=True, slots=True)
class ReactionMarketPoint:
    timestamp: datetime
    close: Decimal
    turnover: Decimal

    def __post_init__(self) -> None:
        _require_aware(self.timestamp, "timestamp")


@dataclass(frozen=True, slots=True)
class ReactionSourceData:
    stock_points: tuple[ReactionMarketPoint, ...]
    benchmark_points: tuple[ReactionMarketPoint, ...]
    session_minutes: tuple[datetime, ...]
    benchmark_proof: "BenchmarkSourceProof"
    session_id: str
    source_checksum: str


@dataclass(frozen=True, slots=True)
class NewsArticleCandidate:
    title: str
    description: str
    published_at: datetime
    original_url: str | None
    naver_url: str

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ValueError("title must not be empty")
        _require_aware(self.published_at, "published_at")
        offset = self.published_at.utcoffset()
        if offset is None or not NAVER_OFFSET_MIN <= offset <= NAVER_OFFSET_MAX:
            raise ValueError(
                "published_at UTC offset is outside Naver's supported range"
            )

    @property
    def canonical_url(self) -> str:
        return self.original_url or self.naver_url


@dataclass(frozen=True, slots=True)
class DiscoveredNewsArticle:
    sample_id: str
    article_id: str
    title: str
    description: str
    published_at: datetime
    original_url: str | None
    naver_url: str | None
    canonical_url: str
    matched_alias_ids: tuple[str, ...]
    matched_call_ordinals: tuple[int, ...]
    # "naver" (Naver date search) or "rss" (shared rss_items pipeline).
    source: str = "naver"

    def __post_init__(self) -> None:
        _require_aware(self.published_at, "published_at")
        if self.source not in {"naver", "rss"}:
            raise ValueError("source must be 'naver' or 'rss'")


@dataclass(frozen=True, slots=True)
class NewsDiscoveryResult:
    security_id: str
    selected_candle_at: datetime
    plan: DiscoveryPlan
    executed_call_count: int
    complete: bool
    articles: tuple[DiscoveredNewsArticle, ...]

    def __post_init__(self) -> None:
        _require_aware(self.selected_candle_at, "selected_candle_at")
        if self.executed_call_count != self.plan.expected_call_count:
            raise ValueError("executed discovery calls must match the frozen plan")
        if not self.complete:
            raise ValueError("partial news discovery results must not be returned")


@dataclass(frozen=True, slots=True)
class BenchmarkSourceProof:
    security_market: str
    benchmark_name: str
    benchmark_code: str
    provider: str
    api_id: str
    endpoint_path: str
    response_key: str
    source_version: str


_KIWOOM_BENCHMARKS = {
    "KOSPI": ("KOSPI", "001"),
    "KOSDAQ": ("KOSDAQ", "101"),
}


def approved_kiwoom_benchmark(security_market: str) -> BenchmarkSourceProof:
    """Return the explicit Kiwoom industry-minute ownership proof."""

    try:
        benchmark_name, benchmark_code = _KIWOOM_BENCHMARKS[security_market]
    except KeyError as error:
        raise ValueError("no approved Kiwoom benchmark for security market") from error
    return BenchmarkSourceProof(
        security_market=security_market,
        benchmark_name=benchmark_name,
        benchmark_code=benchmark_code,
        provider="kiwoom-rest",
        api_id="ka20005",
        endpoint_path="/api/dostk/chart",
        response_key="inds_min_pole_qry",
        source_version="kiwoom-rest-spec-2026-06",
    )


def build_discovery_plan(
    *,
    window_start: datetime,
    window_end: datetime,
    aliases: tuple[CatalogAlias, ...],
    max_terms: int = 3,
) -> DiscoveryPlan:
    """Build the deterministic alias-by-provider-date Naver call matrix."""

    _require_aware(window_start, "window_start")
    _require_aware(window_end, "window_end")
    if window_end < window_start:
        raise ValueError("window_end must be on or after window_start")
    if max_terms < 1:
        raise ValueError("max_terms must be positive")

    normalized: dict[str, CatalogAlias] = {}
    for alias in aliases:
        term = _normalize_term(alias.term)
        if not term:
            raise ValueError("alias term must not be empty")
        candidate = CatalogAlias(
            alias_id=alias.alias_id,
            term=term,
            valid_from=alias.valid_from,
            valid_to=alias.valid_to,
            source=alias.source,
            historical_name_status=alias.historical_name_status,
        )
        existing = normalized.get(term.casefold())
        if existing is None or candidate.alias_id < existing.alias_id:
            normalized[term.casefold()] = candidate

    ordered_aliases = tuple(
        sorted(
            normalized.values(), key=lambda item: (item.term.casefold(), item.alias_id)
        )
    )
    if len(ordered_aliases) > max_terms:
        raise ValueError("alias term cap exceeded")

    start_utc = window_start.astimezone(timezone.utc)
    end_utc = window_end.astimezone(timezone.utc)
    first_date = (start_utc + NAVER_OFFSET_MIN).date()
    last_date = (end_utc + NAVER_OFFSET_MAX).date()
    provider_dates = tuple(
        first_date + timedelta(days=offset)
        for offset in range((last_date - first_date).days + 1)
    )

    calls = tuple(
        DiscoveryCall(index, alias.alias_id, alias.term, provider_date)
        for index, (alias, provider_date) in enumerate(
            (
                (alias, provider_date)
                for alias in ordered_aliases
                for provider_date in provider_dates
            ),
            start=1,
        )
    )
    return DiscoveryPlan(
        version="naver-discovery-plan-v1",
        window_start=window_start.astimezone(KST),
        window_end=window_end.astimezone(KST),
        offset_min_minutes=-12 * 60,
        offset_max_minutes=14 * 60,
        calls=calls,
    )


def candle_identity_checksum(candles: tuple[IntelligenceCandle, ...]) -> str:
    payload = [
        {
            **asdict(candle),
            "timestamp": candle.timestamp.isoformat(),
            "open": str(candle.open),
            "high": str(candle.high),
            "low": str(candle.low),
            "close": str(candle.close),
            "turnover": str(candle.turnover),
        }
        for candle in candles
    ]
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _normalize_term(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split())


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
