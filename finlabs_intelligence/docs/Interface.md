# FinLabs News Intelligence Python 인터페이스 설계

> 기존 `modules/` 계층과 현재 뉴스 모듈을 유지하면서 수집·분류·후보·feature·label·학습·평가를 교체 가능한 계약으로 연결하기 위한 Python API 설계

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 데이터 계약 | [Training Data Model](./TrainDataTable.md), [Feature Dictionary](./FeatureDictionary.md) |
| 전환 계획 | [Migration](./Migration.md) |
| 실행 백로그 | [Implementation Backlog](./Tasks.md) |
| 설계 상태 | Target interface — 현재 구현과 계획을 명시적으로 구분 |
| 기준 시각 | `t0 = first_seen_at` |
| 핵심 원칙 | 순수 DTO·Protocol, 의존성 주입, orchestration만 write 조정 |

## 1. 목적과 적용 범위

이 문서는 향후 구현의 Python 경계를 정의한다. 모든 예시는 interface shape를 설명하기 위한 설계 코드이며, 현재 import 가능한 API로 간주하지 않는다. 현재 구현 여부는 각 절과 [Implementation Backlog](./Tasks.md)에서 확인한다.

인터페이스는 다음 목표를 가진다.

1. 네이버·RSS 등 provider별 결과를 canonical news로 변환한다.
2. 이벤트·후보·feature·label 생성기를 저장소와 분리한다.
3. 학습과 serving에서 동일 feature·model artifact를 사용한다.
4. orchestration이 transaction, idempotency, 실행 이력과 실패 경계를 소유한다.
5. 외부 패키지가 안정적인 public API만 import하게 한다.

## 2. 계층과 패키지 배치

새로운 top-level `finlabs_news/` 패키지를 만들지 않는다. 현재 저장소의 target architecture를 따른다.

```text
modules/
├─ domain/
│  └─ news_intelligence.py       # 순수 canonical DTO·enum·Protocol
├─ news/
│  ├─ naver/                     # 현재 구현: 독립 provider client
│  ├─ trigger/                   # 계획: 텍스트 → event signal
│  ├─ candidates/                # 계획: entity·mapping → candidates
│  ├─ features/                  # 계획: 주입된 시세 → feature rows
│  └─ labels/                    # 계획: 주입된 시세 → label rows
├─ storage/
│  └─ news_intelligence.py       # 계획: SQL·repository 구현
└─ orchestration/
   └─ news_intelligence.py       # 계획: use case, transaction, run log

finlabs_cli/                     # 필요 시 얇은 transport
dashboard/                       # read use case만 호출
research/                        # orchestration query 또는 export artifact 사용
```

### 2.1 책임

| 계층 | 소유 | 금지 |
|---|---|---|
| `domain` | 불변 DTO, enum, Protocol | DB·HTTP·filesystem·모델 import |
| `news.naver` | 인증 header, HTTP, 응답 parsing, provider 오류 | DB write, model inference, 환경변수 직접 조회 |
| `news.trigger/candidates/features/labels` | 결정적 변환·산식 | 전역 DB 접근, CLI 출력, transaction 관리 |
| `storage` | PostgreSQL SQL, repository, schema version | provider client, 분류·모델 로직 |
| `orchestration` | use case, 의존성 조립, write·run log | provider별 parsing, raw SQL |
| CLI/API/dashboard | 입력 검증·표현 | feature 산식, SQL, 직접 모델 학습 |

현재 `modules/news`의 pipeline과 DB 접근은 역사적으로 결합되어 있다. 신규 interface는 이를 즉시 삭제하지 않고 [Migration](./Migration.md)의 dual-write·cutover 절차로 분리한다.

## 3. 설계 원칙

1. 공개 DTO는 `@dataclass(frozen=True, slots=True)`를 기본으로 한다.
2. collection은 변경 가능한 `list`보다 `tuple` 또는 `Sequence`로 노출한다.
3. 시간은 timezone-aware `datetime`, 날짜 검색은 `date`를 사용한다.
4. 종목 식별자는 항상 `(market, ticker)`다.
5. 수익률은 소수 단위, 금액은 KRW, 점수는 0~1 범위를 명시한다.
6. `None`은 “없음/알 수 없음”이며 0 또는 빈 문자열과 구분한다.
7. feature와 label DTO를 분리하고 미래 field를 feature interface에 넣지 않는다.
8. provider·processor·repository는 Protocol로 주입하고 구체 구현을 내부에서 생성하지 않는다.
9. batch API는 순서, 부분 실패, transaction 범위를 문서화한다.
10. DataFrame은 boundary DTO가 아니다. 학습 adapter 내부 또는 export에서만 사용한다.

## 4. 공통 값 객체

다음 코드는 목표 계약의 축약 예시다.

```python
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Mapping


@dataclass(frozen=True, slots=True, order=True)
class SecurityId:
    market: str
    ticker: str


@dataclass(frozen=True, slots=True)
class CanonicalNewsItem:
    news_id: str
    provider: str
    source_name: str | None
    title: str
    description: str
    canonical_url: str
    provider_url: str | None
    published_at: datetime
    first_seen_at: datetime
    collected_at: datetime
    normalized_text_hash: str
    ingestion_version: str


SessionType = Literal["pre_market", "regular", "after_market", "closed_day"]
Split = Literal["train", "valid", "test"]
```

필수 validation:

- 모든 ID·version은 공백이 아니다.
- timestamp는 timezone-aware다.
- `first_seen_at <= collected_at`이다.
- canonical URL은 비어 있지 않다.
- 네이버 입력은 제목과 `description`만 요구하며 기사 전문을 요구하지 않는다.

## 5. Trigger·Entity·Candidate DTO

### 5.1 Trigger result

```python
@dataclass(frozen=True, slots=True)
class TriggerSignal:
    news_id: str
    event_type: str
    polarity: Literal["positive", "negative", "neutral"]
    certainty: Literal["C0", "C1", "C2", "C3"]
    immediacy: Literal["I0", "I1", "I2", "I3"]
    scope: Literal["single_stock", "sector", "theme", "market"]
    novelty_score: float | None
    trigger_probability: float
    is_posthoc_article: bool
    taxonomy_version: str
    model_version: str
    prompt_version: str
    generated_at: datetime
```

`event_type`은 `modules/news/schema/event.py` taxonomy v1과 일치해야 한다. `trigger_probability`와 사후 `is_strong_reaction`은 다른 계약이다.

### 5.2 Entity와 mapping

```python
@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    news_id: str
    entity_text: str
    normalized_text: str
    entity_type: str
    start_offset: int | None
    end_offset: int | None
    confidence: float
    extractor_version: str


@dataclass(frozen=True, slots=True)
class LinkedSecurity:
    entity_text: str
    security: SecurityId
    company_name: str
    mapping_type: str
    confidence: float
    mapping_version: str
    valid_from: datetime
    valid_to: datetime | None
```

Ticker linker는 반드시 기사 `t0`를 입력받아 해당 시점에 유효한 mapping만 반환한다.

### 5.3 Candidate

```python
@dataclass(frozen=True, slots=True)
class NewsCandidate:
    news_id: str
    security: SecurityId
    relation_type: str
    relation_reason: str
    candidate_score: float
    candidate_rank: int
    direct_mention: bool
    title_mention: bool
    theme_match_score: float | None
    sector_match_score: float | None
    relation_strength: float | None
    taxonomy_version: str
    trigger_model_version: str
    trigger_prompt_version: str
    extractor_version: str
    mapping_version: str
    candidate_version: str
```

후보 순서는 `candidate_score DESC, market ASC, ticker ASC`로 결정한다. 유동성과 미래 반응은 `candidate_score` 산식에 넣지 않는다.

## 6. Feature·Label DTO

### 6.1 Market feature row

모든 feature를 dataclass field로 중복 선언하기보다 고정 schema와 typed value map을 함께 사용할 수 있다. 단, 임의 key를 허용하지 않고 feature registry로 검증한다.

```python
FeatureValue = float | int | bool | str | None


@dataclass(frozen=True, slots=True)
class MarketFeatureRow:
    news_id: str
    security: SecurityId
    t0: datetime
    feature_cutoff_at: datetime
    session_type: SessionType
    values: Mapping[str, FeatureValue]
    missing_flags: Mapping[str, bool]
    feature_version: str
```

필수 invariant:

- `feature_cutoff_at <= t0`
- `values` key는 해당 `feature_version` registry allowlist와 동일
- 미래 수익률, label, split 정보는 포함하지 않음
- mutable dict를 그대로 보관하지 않고 immutable mapping 또는 defensive copy 사용

### 6.2 Reaction label

```python
@dataclass(frozen=True, slots=True)
class ReactionLabel:
    news_id: str
    security: SecurityId
    t0: datetime
    label_window_start: datetime
    label_window_end: datetime
    benchmark_id: str
    future_max_return_30m: float | None
    future_close_return_30m: float | None
    future_max_excess_return_30m: float | None
    future_turnover_z_30m: float | None
    reaction_score: float | None
    reaction_class: Literal["strong", "medium", "weak", "none"] | None
    is_strong_reaction: bool | None
    exclusion_reason: str | None
    label_version: str
```

`label_window_start >= t0`와 `label_window_end > label_window_start`를 강제한다. window가 불완전하면 숫자를 보간하지 않고 exclusion reason을 기록하며 `reaction_class`와 `is_strong_reaction`은 `None`으로 둔다.

## 7. 현재 구현된 네이버 공개 API

현재 재사용 가능한 interface는 다음과 같다.

```python
from datetime import date

from modules.news.naver import NaverNewsClient


with NaverNewsClient(
    client_id="...",
    client_secret="...",
) as client:
    articles = client.search("삼성전자", date(2026, 6, 18))
```

```python
@dataclass(frozen=True, slots=True)
class NaverNewsArticle:
    title: str
    description: str
    published_at: datetime
    original_url: str | None
    naver_url: str

    @property
    def canonical_url(self) -> str: ...
```

- `search()`는 `tuple[NaverNewsArticle, ...]`을 반환한다.
- 날짜 결과의 완전성을 보장할 수 없으면 부분 결과를 반환하지 않는다.
- client는 환경변수를 직접 읽지 않으며 credential을 호출자가 주입한다.
- fake `HttpTransport`를 주입할 수 있다.
- `NaverNewsError` 계층을 공개 실패 계약으로 사용한다.

Provider DTO를 canonical news로 변환하고 `first_seen_at`을 부여하는 책임은 수집 orchestration에 있다. `NaverNewsClient`에 DB write나 FinLabs domain 의존성을 추가하지 않는다.

## 8. Provider와 processor Protocol

### 8.1 검색 source

```python
from datetime import date
from typing import Protocol, Sequence


class DatedNewsSearch(Protocol):
    def search(self, keyword: str, published_on: date) -> Sequence[object]: ...
```

공통 orchestration이 `object`를 직접 해석하지 않도록 provider마다 mapper를 함께 주입한다.

```python
class NewsItemMapper(Protocol):
    def to_canonical(
        self,
        provider_item: object,
        *,
        first_seen_at: datetime,
        collected_at: datetime,
    ) -> CanonicalNewsItem: ...
```

### 8.2 Trigger·entity·candidate processor

```python
class TriggerClassifier(Protocol):
    @property
    def taxonomy_version(self) -> str: ...

    @property
    def model_version(self) -> str: ...

    def classify(self, news: CanonicalNewsItem) -> TriggerSignal: ...


class EntityExtractor(Protocol):
    @property
    def extractor_version(self) -> str: ...

    def extract(self, news: CanonicalNewsItem) -> tuple[ExtractedEntity, ...]: ...


class SecurityLinker(Protocol):
    def link(
        self,
        entities: Sequence[ExtractedEntity],
        *,
        as_of: datetime,
    ) -> tuple[LinkedSecurity, ...]: ...


class CandidateGenerator(Protocol):
    @property
    def candidate_version(self) -> str: ...

    def generate(
        self,
        news: CanonicalNewsItem,
        trigger: TriggerSignal,
        entities: Sequence[ExtractedEntity],
        linked: Sequence[LinkedSecurity],
    ) -> tuple[NewsCandidate, ...]: ...
```

Batch 최적화가 필요하면 별도 batch adapter를 추가하되 단건 의미와 ordering을 바꾸지 않는다.

## 9. Market data reader와 builder Protocol

Feature와 label builder는 raw SQL을 실행하지 않고 공통 market reader를 주입받는다.

```python
@dataclass(frozen=True, slots=True)
class MinuteBar:
    security: SecurityId
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float


class PointInTimeMarketReader(Protocol):
    def minute_bars(
        self,
        security: SecurityId,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[MinuteBar, ...]: ...

    def benchmark_bars(
        self,
        benchmark_id: str,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[MinuteBar, ...]: ...
```

Reader는 timestamp 오름차순과 중복 없는 bar를 보장한다. 빈 tuple은 정상적인 “데이터 없음”이며 builder가 exclusion을 결정한다.

```python
class MarketFeatureBuilder(Protocol):
    @property
    def feature_version(self) -> str: ...

    def build(
        self,
        news: CanonicalNewsItem,
        candidate: NewsCandidate,
    ) -> MarketFeatureRow: ...


class ReactionLabelBuilder(Protocol):
    @property
    def label_version(self) -> str: ...

    def build(
        self,
        news: CanonicalNewsItem,
        candidate: NewsCandidate,
    ) -> ReactionLabel: ...
```

두 builder가 같은 객체에서 feature와 label을 동시에 반환하지 않게 해 미래 데이터 경계를 명확히 한다.

## 10. Repository Protocol

Repository interface는 domain DTO만 받고 반환한다. SQL, connection, DataFrame과 provider DTO를 노출하지 않는다.

### 10.1 뉴스·파생 결과

```python
class NewsRepository(Protocol):
    def put_if_absent(self, item: CanonicalNewsItem) -> bool: ...

    def get(self, news_id: str) -> CanonicalNewsItem | None: ...

    def list_first_seen(
        self,
        *,
        start: datetime,
        end: datetime,
        after_news_id: str | None = None,
        limit: int = 1_000,
    ) -> tuple[CanonicalNewsItem, ...]: ...


class TriggerRepository(Protocol):
    def put(self, signal: TriggerSignal) -> None: ...

    def get(
        self,
        news_id: str,
        *,
        taxonomy_version: str,
        model_version: str,
    ) -> TriggerSignal | None: ...


class CandidateRepository(Protocol):
    def replace_version(
        self,
        news_id: str,
        *,
        candidate_version: str,
        candidates: Sequence[NewsCandidate],
    ) -> int: ...

    def list_for_news(
        self,
        news_id: str,
        *,
        candidate_version: str,
    ) -> tuple[NewsCandidate, ...]: ...
```

`put_if_absent`가 `False`를 반환해도 `first_seen_at`을 갱신하지 않는다. 동일 version 후보 교체는 하나의 transaction에서 delete+insert 또는 merge semantics를 보장한다.

### 10.2 Feature·label·dataset

```python
class FeatureRepository(Protocol):
    def put_many(self, rows: Sequence[MarketFeatureRow]) -> int: ...

    def list_for_news(
        self,
        news_id: str,
        *,
        feature_version: str,
    ) -> tuple[MarketFeatureRow, ...]: ...


class LabelRepository(Protocol):
    def put_many(self, rows: Sequence[ReactionLabel]) -> int: ...

    def list_for_news(
        self,
        news_id: str,
        *,
        label_version: str,
    ) -> tuple[ReactionLabel, ...]: ...


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_version: str
    source_snapshot: Mapping[str, str]
    taxonomy_version: str
    trigger_model_version: str
    trigger_prompt_version: str
    extractor_version: str
    cluster_version: str
    mapping_version: str
    candidate_version: str
    feature_version: str
    label_version: str
    split_config: Mapping[str, str]
    exclusion_config: Mapping[str, object]
    checksum: str


class DatasetRepository(Protocol):
    def register(self, manifest: DatasetManifest) -> None: ...

    def iter_rows(
        self,
        dataset_version: str,
        *,
        split: Split,
        batch_size: int = 10_000,
    ) -> "Iterator[tuple[MarketFeatureRow, ReactionLabel]]": ...
```

대규모 dataset을 한 번에 list 또는 DataFrame으로 반환하지 않는다. stable ordering과 cursor/batch semantics를 명시한다.

## 11. Transaction 경계

여러 repository write를 묶기 위해 connection 객체를 각 interface에 노출하지 않고 Unit of Work를 사용한다.

```python
class NewsIntelligenceUnitOfWork(Protocol):
    news: NewsRepository
    triggers: TriggerRepository
    candidates: CandidateRepository
    features: FeatureRepository
    labels: LabelRepository

    def __enter__(self) -> "NewsIntelligenceUnitOfWork": ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

Orchestration만 Unit of Work를 연다. processor와 provider client는 transaction을 알지 못한다. PostgreSQL 단일 writer 직렬화(인프로세스 FIFO + `pg_advisory_xact_lock`)는 concrete UoW 또는 orchestration runner가 소유한다.

## 12. Orchestration command·result

### 12.1 검색·적재

```python
@dataclass(frozen=True, slots=True)
class SearchNewsCommand:
    keyword: str
    published_on: "date"
    provider: str = "naver"


@dataclass(frozen=True, slots=True)
class IngestNewsResult:
    run_id: str
    searched_count: int
    inserted_count: int
    existing_count: int
    failed_count: int
    complete: bool


def search_and_ingest_news(
    command: SearchNewsCommand,
    *,
    source: DatedNewsSearch,
    mapper: NewsItemMapper,
    uow_factory: "Callable[[], NewsIntelligenceUnitOfWork]",
    clock: "Callable[[], datetime]",
) -> IngestNewsResult: ...
```

Provider가 incomplete search를 보고하면 `complete=False` 결과로 정상 저장하지 않고 공개 예외로 전체 operation을 실패시킨다.

### 12.2 Trigger·candidate 실행

```python
@dataclass(frozen=True, slots=True)
class BuildCandidatesCommand:
    news_id: str
    taxonomy_version: str
    candidate_version: str


@dataclass(frozen=True, slots=True)
class BuildCandidatesResult:
    run_id: str
    news_id: str
    candidate_count: int
    unresolved_entity_count: int
    skipped: bool
```

Orchestration은 news load → trigger → entity → point-in-time link → candidate → write를 조정한다. 같은 version 결과가 이미 완전하면 skip하고, force 재생성은 별도 명시 옵션으로만 허용한다.

### 12.3 Feature·label·dataset

Feature와 label build command는 분리한다.

```python
@dataclass(frozen=True, slots=True)
class BuildFeaturesCommand:
    news_ids: tuple[str, ...]
    candidate_version: str
    feature_version: str


@dataclass(frozen=True, slots=True)
class BuildLabelsCommand:
    news_ids: tuple[str, ...]
    candidate_version: str
    label_version: str
```

각 result는 processed, inserted, skipped, excluded, failed count와 bounded error summary를 반환한다. 실패한 일부 row를 숨기고 성공으로 표시하지 않는다.

## 13. 모델·랭킹 interface

모델 artifact는 model file 하나가 아니라 feature schema와 전처리를 포함한다.

```python
@dataclass(frozen=True, slots=True)
class ModelManifest:
    model_version: str
    dataset_version: str
    feature_version: str
    label_version: str
    feature_names: tuple[str, ...]
    artifact_uri: str
    artifact_checksum: str
    metrics: Mapping[str, float]


class ReactionModel(Protocol):
    @property
    def manifest(self) -> ModelManifest: ...

    def predict_proba(
        self,
        rows: Sequence[MarketFeatureRow],
    ) -> tuple[float, ...]: ...


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    news_id: str
    security: SecurityId
    rank: int
    reaction_probability: float
    candidate_score: float
    main_factors: tuple[str, ...]
    warnings: tuple[str, ...]
    model_version: str
    feature_version: str
```

Ranker는 확률 내림차순, candidate score 내림차순, market, ticker 순으로 tie를 해소한다. `main_factors`는 인과 설명이 아니라 모델 기여 요약이다.

## 14. Dataset·training interface

```python
@dataclass(frozen=True, slots=True)
class BuildDatasetCommand:
    dataset_version: str
    source_snapshot: Mapping[str, str]
    taxonomy_version: str
    trigger_model_version: str
    trigger_prompt_version: str
    extractor_version: str
    cluster_version: str
    mapping_version: str
    candidate_version: str
    feature_version: str
    label_version: str
    train_end: datetime
    valid_end: datetime
    test_end: datetime


@dataclass(frozen=True, slots=True)
class TrainModelCommand:
    dataset_version: str
    model_version: str
    target: Literal["is_strong_reaction"] = "is_strong_reaction"
```

Dataset builder는 cluster-aware time split과 checksum을 생성한다. Trainer는 train으로 적합하고 valid로 선택·calibration하며 test를 최종 평가에만 사용한다. 학습 library 객체는 orchestration result로 직접 반환하지 않는다.

## 15. Backtest interface

```python
@dataclass(frozen=True, slots=True)
class BacktestConfig:
    backtest_version: str
    dataset_version: str
    model_version: str
    execution_delay_minutes: int
    holding_trading_minutes: int
    top_k: tuple[int, ...]
    commission_bps: float
    tax_bps: float
    slippage_bps: float
    max_concurrent_positions: int


@dataclass(frozen=True, slots=True)
class BacktestResult:
    run_id: str
    scenario: str
    prediction_count: int
    executed_count: int
    excluded_count: int
    metrics: Mapping[str, float]
    artifact_uri: str
    manifest_checksum: str


class BacktestRunner(Protocol):
    def run(self, config: BacktestConfig) -> BacktestResult: ...
```

Runner는 [Backtest](./Backtest.md)의 Ranking·Tradable·Conservative 시나리오를 분리한다. 미래 최대 고가를 체결 수익률로 사용하지 않는다.

## 16. 오류 계약

오류는 원인과 retry 가능성을 보존하되 credential·원문·내부 SQL을 노출하지 않는다.

```text
NewsIntelligenceError
├─ ContractError                 # 입력·DTO invariant 위반, retry 불가
├─ SourceError                   # provider 실패
│  ├─ AuthenticationError
│  ├─ RateLimitError
│  ├─ IncompleteResultError
│  └─ MalformedSourceError
├─ MappingError                  # 결정적 mapping 실패 또는 충돌
├─ MarketDataUnavailableError    # feature/label 원천 부족
├─ PersistenceError              # transaction·constraint 실패
├─ VersionMismatchError          # artifact·schema version 불일치
└─ DataLeakageError              # point-in-time·split invariant 위반
```

네이버 client의 기존 `NaverNewsError` 계층은 provider 경계에서 유지한다. Orchestration은 필요할 때 공통 error로 감싸되 원래 exception을 cause로 보존한다.

## 17. 동기·비동기 정책

- 현재 네이버 client와 PostgreSQL 접근은 동기 interface를 유지한다.
- CPU/DB batch를 임의로 `async`로 감싸지 않는다.
- FastAPI 등 async transport는 thread worker 또는 job orchestration을 통해 동기 use case를 호출한다.
- 단일 writer를 직렬화하며(인프로세스 FIFO + `pg_advisory_xact_lock`) 병렬 write transaction을 만들지 않는다.
- 모델 batch inference 내부 병렬성은 config와 artifact에 기록한다.

## 18. Public API와 호환성

### 안정적 public surface

- `modules.news.naver`의 client, article DTO, 공개 오류
- 향후 `modules.domain.news_intelligence`의 canonical DTO·Protocol
- 향후 `modules.orchestration.news_intelligence`의 command·result와 use case

### 내부 구현

- SQL statement, PostgreSQL connection
- parser helper, feature 산식 helper
- concrete LightGBM object
- migration mapper와 compatibility view

Public symbol은 각 package `__init__.py`에서 명시적으로 export한다. field 삭제·의미 변경은 호환성 변경이며 deprecation 기간 또는 새 major contract version이 필요하다.

## 19. CLI·API 연결 원칙

현재 구현되지 않은 명령을 사용 가능하다고 문서화하지 않는다. 향후 transport를 추가할 때는 다음 command에 1:1로 매핑한다.

```text
search-and-ingest
build-candidates
build-features
build-labels
build-dataset
train-model
run-backtest
```

CLI는 Typer를 사용하고 `python -m finlabs_cli` 계약을 따른다. 별도 `finlabs-news` console script를 만들지 않는다. API는 command를 직접 재구현하지 않고 동일 orchestration use case를 호출한다.

## 20. 테스트 계약

| 경계 | 필수 테스트 |
|---|---|
| DTO | naive timestamp, 빈 ID, score 범위, window invariant 거부 |
| Provider | mock HTTP, pagination 완전성, timeout·429·5xx, 순서·dedup |
| Mapper | canonical ID, URL, `first_seen_at`, text hash 결정성 |
| Trigger | taxonomy 제한, version, 동일 입력 재현성 |
| Linker | point-in-time mapping, 별칭 충돌, 미매핑 처리 |
| Candidate | relation 근거, 미래값 미사용, tie ordering |
| Feature | `feature_cutoff_at <= t0`, 미래 bar 주입 불변성 |
| Label | window·benchmark·경계값, 불완전 horizon 제외 |
| Repository | unique key, idempotency, ordering, transaction rollback |
| Dataset | 시간 split, cluster 격리, train-only transform |
| Model | manifest mismatch 거부, feature ordering, calibration |
| Backtest | entry 시각, 비용, 미체결, hand-calculated metric |
| Architecture | forbidden import와 raw SQL 위치 검사 |

실제 네이버·증권 API는 단위 테스트에서 호출하지 않는다.

## 21. 구현 순서

1. canonical DTO·validation과 current-to-target mapper
2. repository Protocol과 PostgreSQL concrete repository
3. search-and-ingest orchestration과 immutable first-seen
4. Trigger·entity·candidate processor
5. point-in-time market reader와 feature builder
6. 별도 label builder
7. dataset manifest·split·export
8. baseline·model artifact·ranker
9. backtest runner
10. CLI/API read surface와 shadow 운영

세부 ID와 의존성은 [Implementation Backlog](./Tasks.md)를 따른다.

## 22. 완료 기준

1. public DTO와 Protocol이 저장소·HTTP·모델 library에 의존하지 않는다.
2. 네이버 client는 독립 재사용성을 유지하고 canonical 변환은 orchestration에서 수행한다.
3. 종목 mapping은 `(market, ticker, as_of)` 계약을 강제한다.
4. feature와 label interface가 분리되고 미래 field가 feature에 들어가지 않는다.
5. repository가 stable ordering, idempotency, version key와 transaction semantics를 보장한다.
6. dataset·model·backtest artifact가 manifest와 checksum으로 연결된다.
7. CLI/API는 orchestration command·result만 사용한다.
8. 현재 구현과 계획 API가 문서에서 명확히 구분된다.
9. interface별 contract test와 architecture boundary test가 통과한다.
