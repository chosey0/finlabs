# FinLabs News Intelligence 학습 데이터 모델 설계서

> 뉴스 입력, 이벤트 해석, 후보 종목, 시점 특징과 미래 반응 라벨을 분리해 학습 데이터셋을 재현 가능하게 만드는 논리·물리 데이터 설계

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 설계 상태 | Logical target schema — 실제 DDL·repository 미구현 |
| 연계 문서 | [News Trigger Layer](./NewsTriggerLayer.md), [Market Reaction Layer](./MarketReactionLayer.md), [Feature Dictionary](./FeatureDictionary.md), [Backtest](./Backtest.md), [Migration](./Migration.md) |
| 학습 단위 | `(news_id, market, ticker, t0)` |
| 기준 시각 | `t0 = first_seen_at` |
| 저장 원칙 | 원천·파생·라벨·학습 snapshot 분리 |
| 재현 원칙 | 모든 파생 행에 생성 규칙 또는 모델 버전 기록 |

## 1. 설계 목표

최종 목표는 뉴스 1건과 후보 종목 1개를 하나의 학습 샘플로 만들고, 그 샘플을 동일한 입력과 버전으로 다시 생성할 수 있게 하는 것이다.

```text
(news_id, market, ticker, t0)
```

데이터 모델은 다음 질문에 답할 수 있어야 한다.

- 시스템은 이 뉴스를 언제 처음 알았는가?
- 어떤 텍스트와 taxonomy로 이벤트를 분류했는가?
- 왜 이 종목이 후보에 포함됐는가?
- `t0` 시점에 사용할 수 있었던 시장 특징은 무엇인가?
- 어떤 미래 window와 benchmark로 라벨을 만들었는가?
- 어떤 split·dataset version으로 모델에 입력됐는가?

## 2. 핵심 원칙

1. **Point-in-time**: 특징은 `t0` 이후 값을 포함하지 않는다.
2. **Immutable first-seen**: 재수집이 `first_seen_at`을 덮어쓰지 않는다.
3. **Source of truth 분리**: 원천 뉴스, 파생 이벤트, 후보, 특징, 라벨을 별도 관리한다.
4. **Version everything**: taxonomy·추출기·후보·특징·라벨·dataset 버전을 기록한다.
5. **No full-text scraping**: 네이버 소스는 제목과 `description`만 저장한다.
6. **Shared market ownership**: 종목 마스터와 원시 시세는 공통 market 계층이 소유하며 뉴스 모듈이 복제하지 않는다.
7. **Rebuildable training set**: `training_pairs`는 source of truth가 아니라 버전된 snapshot 또는 materialized output이다.

## 3. 논리 데이터 흐름

```text
news_items ───────────────┬───────────────┐
    ↓                     ↓               │
news_events          news_entities        │
                          ↓               │
                  entity_ticker_map       │
                          ↓               │
                    news_candidates       │
                          ↓               │
market data ─────── market_features       │
                          ↓               ↓
                    reaction_labels       │
                          └──────┬────────┘
                                 ↓
                         dataset_members
                                 ↓
                         training_pairs
```

## 4. 테이블 목록과 책임

| 테이블 | 책임 | Source of truth |
|---|---|:---:|
| `news_items` | 수집된 뉴스 메타데이터와 최초 관측시각 | 예 |
| `news_clusters` | 중복·동일 사건 군집 | 예 |
| `news_events` | 이벤트 taxonomy와 Trigger 출력 | 파생 |
| `news_entities` | 텍스트에서 추출한 entity | 파생 |
| `entity_ticker_map` | 시점 유효 entity-종목 매핑 | 예 |
| `theme_ticker_map` | 시점 유효 테마-종목 매핑 | 예 |
| `news_candidates` | 뉴스별 후보와 관계 근거 | 파생 |
| `market_features` | `t0` 이전 시장 특징 | 파생 |
| `reaction_labels` | `t0` 이후 관측 라벨 | 파생 |
| `dataset_versions` | 데이터셋 생성 설정과 기간 | 예 |
| `dataset_members` | dataset에 포함된 샘플과 split | 파생 snapshot |
| `training_pairs` | 모델 입력용 비정규화 snapshot/view | 파생 snapshot |

`stock_master`와 1분봉·호가 원천 테이블은 FinLabs 공통 market 계층을 참조한다. 뉴스 스키마에 별도 복제본을 만들면 회사명 변경, 상장폐지, corporate action 시점이 어긋날 수 있다.

## 5. 공통 타입과 제약

- 시각: timezone-aware `TIMESTAMPTZ`
- 점수: 0~1이면 `DOUBLE PRECISION`과 `CHECK` 사용
- 종목 식별: `(market, ticker)` 복합키
- 버전: 공백 없는 `TEXT`
- 생성 시간과 모델 기준 시각을 구분
- enum 성격 값은 `CHECK` 또는 reference table로 제한

SQL 예시는 타입·제약을 명확히 표현하기 위해 PostgreSQL 문법을 사용한 논리 설계 초안이다. News Intelligence의 primary 저장소는 PostgreSQL(예: Supabase, RDS, 자체 호스팅)이며 실제 DDL과 migration은 [Migration](./Migration.md)의 저장소 책임과 프로젝트 명명 규칙을 따른다. 레거시 `modules/news` 수집 pipeline의 warehouse는 별도로 DuckDB를 유지한다.

## 6. `news_items`

뉴스 API·RSS에서 얻은 원천 메타데이터를 보존한다.

```sql
CREATE TABLE news_items (
    news_id             TEXT PRIMARY KEY,
    provider            TEXT NOT NULL,
    source_name         TEXT,
    canonical_url       TEXT NOT NULL,
    provider_url        TEXT,
    title               TEXT NOT NULL,
    description         TEXT NOT NULL DEFAULT '',
    published_at        TIMESTAMPTZ NOT NULL,
    first_seen_at       TIMESTAMPTZ NOT NULL,
    collected_at        TIMESTAMPTZ NOT NULL,
    language            TEXT NOT NULL DEFAULT 'ko',
    normalized_text_hash TEXT NOT NULL,
    ingestion_version   TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (provider, canonical_url),
    CHECK (first_seen_at <= collected_at)
);
```

### 정책

- `first_seen_at`은 최초 insert 이후 변경하지 않는다.
- 재수집 시 `collected_at`은 최근 성공 저장 시각으로 갱신하고, 실행별 수집 이력은 별도 ingestion run에 기록한다.
- 네이버 검색 결과는 기사 전문이 없으므로 `raw_body`를 두지 않는다.
- 검색 API의 원래 timezone offset은 애플리케이션 모델에서 보존하고 DB에는 절대시각으로 저장한다.
- 제목·요약 정규화 규칙은 `ingestion_version`으로 추적한다.

## 7. `news_clusters`

전재 기사와 반복 보도를 하나의 중복 또는 사건 cluster로 관리한다.

```sql
CREATE TABLE news_clusters (
    news_id              TEXT NOT NULL REFERENCES news_items(news_id),
    duplicate_cluster_id TEXT NOT NULL,
    event_cluster_id     TEXT,
    is_cluster_primary   BOOLEAN NOT NULL,
    novelty_score        DOUBLE PRECISION,
    cluster_version      TEXT NOT NULL,
    clustered_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (news_id, cluster_version),
    CHECK (novelty_score IS NULL OR novelty_score BETWEEN 0 AND 1)
);
```

- `duplicate_cluster_id`: 사실상 동일한 문서군
- `event_cluster_id`: 같은 사건을 다루는 여러 시점·출처의 기사군
- 동일 cluster는 train/valid/test 중 하나에만 속한다.

## 8. `news_events`

News Trigger Layer의 이벤트 분류 결과를 버전별로 저장한다.

```sql
CREATE TABLE news_events (
    news_id              TEXT NOT NULL REFERENCES news_items(news_id),
    event_type           TEXT NOT NULL,
    polarity             TEXT NOT NULL,
    scope                TEXT NOT NULL,
    certainty            TEXT NOT NULL,
    immediacy            TEXT NOT NULL,
    trigger_probability  DOUBLE PRECISION,
    event_confidence     DOUBLE PRECISION NOT NULL,
    is_posthoc_article   BOOLEAN NOT NULL DEFAULT false,
    model_version        TEXT NOT NULL,
    prompt_version       TEXT NOT NULL,
    taxonomy_version     TEXT NOT NULL,
    generated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (news_id, model_version, prompt_version, taxonomy_version),
    CHECK (polarity IN ('positive', 'negative', 'neutral')),
    CHECK (scope IN ('single_stock', 'sector', 'theme', 'market')),
    CHECK (certainty IN ('C0', 'C1', 'C2', 'C3')),
    CHECK (immediacy IN ('I0', 'I1', 'I2', 'I3')),
    CHECK (trigger_probability IS NULL OR trigger_probability BETWEEN 0 AND 1),
    CHECK (event_confidence BETWEEN 0 AND 1)
);
```

`event_type`은 애플리케이션 taxonomy v1의 닫힌 목록과 동기화한다. DB migration과 코드 enum이 어긋나지 않도록 계약 테스트를 둔다.

## 9. `news_entities`

뉴스 텍스트에서 추출한 entity와 위치를 저장한다.

```sql
CREATE TABLE news_entities (
    entity_id          BIGSERIAL PRIMARY KEY,
    news_id            TEXT NOT NULL REFERENCES news_items(news_id),
    entity_text        TEXT NOT NULL,
    normalized_name    TEXT NOT NULL,
    entity_type        TEXT NOT NULL,
    start_pos          INTEGER,
    end_pos            INTEGER,
    confidence         DOUBLE PRECISION NOT NULL,
    extractor_version  TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (
        (start_pos IS NULL AND end_pos IS NULL)
        OR (start_pos >= 0 AND end_pos > start_pos)
    )
);
```

MVP entity type은 `stock`, `company`, `industry`, `keyword`를 우선 사용한다. 같은 entity가 여러 위치에 등장할 수 있으므로 occurrence row를 보존하고, 동일 `(news_id, extractor_version)`의 재생성은 전체 결과를 transaction으로 교체한다. span을 제공하지 않는 extractor는 애플리케이션 단계에서 `(normalized_name, entity_type)`을 결정적으로 dedup한다. 확장 시 코드의 `ENTITY_TYPES`와 함께 버전을 올린다.

## 10. 시점 유효 매핑 테이블

### 10.1 `entity_ticker_map`

```sql
CREATE TABLE entity_ticker_map (
    map_id            BIGSERIAL PRIMARY KEY,
    normalized_name   TEXT NOT NULL,
    market            TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    mapping_type      TEXT NOT NULL,
    confidence        DOUBLE PRECISION NOT NULL,
    valid_from        DATE NOT NULL,
    valid_to          DATE,
    mapping_version   TEXT NOT NULL,
    source            TEXT NOT NULL,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (confidence BETWEEN 0 AND 1),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (normalized_name, market, ticker, valid_from, mapping_version)
);
```

`mapping_type` 예: `official_name`, `alias`, `brand_owner`, `product_owner`, `manual`.

### 10.2 `theme_ticker_map`

```sql
CREATE TABLE theme_ticker_map (
    map_id             BIGSERIAL PRIMARY KEY,
    theme              TEXT NOT NULL,
    keyword            TEXT NOT NULL,
    market             TEXT NOT NULL,
    ticker             TEXT NOT NULL,
    relation_strength  DOUBLE PRECISION NOT NULL,
    valid_from         DATE NOT NULL,
    valid_to           DATE,
    mapping_version    TEXT NOT NULL,
    source             TEXT NOT NULL,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (relation_strength BETWEEN 0 AND 1),
    CHECK (valid_to IS NULL OR valid_to >= valid_from),
    UNIQUE (theme, keyword, market, ticker, valid_from, mapping_version)
);
```

단순 `is_active`만 두면 과거 기사 재생성 시 현재 관계가 적용된다. 반드시 유효기간을 보존한다.

## 11. `news_candidates`

뉴스와 후보 종목의 연결 결과와 근거를 저장한다.

```sql
CREATE TABLE news_candidates (
    news_id             TEXT NOT NULL REFERENCES news_items(news_id),
    market              TEXT NOT NULL,
    ticker              TEXT NOT NULL,
    relation_type       TEXT NOT NULL,
    relation_reason     TEXT NOT NULL,
    candidate_score     DOUBLE PRECISION NOT NULL,
    candidate_rank      INTEGER NOT NULL,
    direct_mention      BOOLEAN NOT NULL DEFAULT false,
    title_mention       BOOLEAN NOT NULL DEFAULT false,
    theme_match_score   DOUBLE PRECISION,
    sector_match_score  DOUBLE PRECISION,
    relation_strength   DOUBLE PRECISION,
    taxonomy_version    TEXT NOT NULL,
    trigger_model_version TEXT NOT NULL,
    trigger_prompt_version TEXT NOT NULL,
    extractor_version   TEXT NOT NULL,
    mapping_version     TEXT NOT NULL,
    candidate_version   TEXT NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (news_id, market, ticker, candidate_version),
    UNIQUE (news_id, candidate_version, candidate_rank),
    CHECK (candidate_score BETWEEN 0 AND 1),
    CHECK (candidate_rank > 0),
    CHECK (relation_type IN ('direct_mention', 'theme_related', 'sector_peer'))
);
```

후보의 종목 유효성은 공통 point-in-time 종목 마스터로 확인한다. 후보 생성 단계에서는 미래 가격 반응을 사용하지 않는다.

## 12. 공통 시장 데이터 의존성

뉴스 스키마는 다음 원천을 공통 market 계층에서 읽는다.

- point-in-time 종목 마스터와 섹터 분류
- 1분 OHLCV와 거래대금
- 시장·섹터 benchmark
- 거래정지, VI, corporate action과 거래일 캘린더

이 문서에서 별도 `market_snapshot` 테이블을 정의하지 않는다. 원시 시세 복제는 데이터 불일치와 보정 중복을 만든다.

## 13. `market_features`

`t0` 직전까지의 모델 입력 특징을 저장한다.

```sql
CREATE TABLE market_features (
    news_id               TEXT NOT NULL REFERENCES news_items(news_id),
    market                TEXT NOT NULL,
    ticker                TEXT NOT NULL,
    t0                    TIMESTAMPTZ NOT NULL,
    session_type          TEXT NOT NULL,
    session_bucket        TEXT,
    return_1m             DOUBLE PRECISION,
    return_5m             DOUBLE PRECISION,
    return_15m            DOUBLE PRECISION,
    pre_return_5m         DOUBLE PRECISION,
    volume_z_1m           DOUBLE PRECISION,
    volume_z_5m           DOUBLE PRECISION,
    turnover_z_5m         DOUBLE PRECISION,
    turnover_ratio_5m     DOUBLE PRECISION,
    volatility_5m         DOUBLE PRECISION,
    volatility_15m        DOUBLE PRECISION,
    market_return_5m      DOUBLE PRECISION,
    sector_return_5m      DOUBLE PRECISION,
    sector_turnover_z_5m  DOUBLE PRECISION,
    avg_turnover_20d      NUMERIC,
    market_cap            NUMERIC,
    minutes_from_open     INTEGER,
    minutes_to_close      INTEGER,
    pre_move_flag         BOOLEAN NOT NULL,
    liquidity_pass        BOOLEAN NOT NULL,
    missing_flags         JSONB NOT NULL DEFAULT '{}'::jsonb,
    feature_cutoff_at     TIMESTAMPTZ NOT NULL,
    feature_version       TEXT NOT NULL,
    generated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (news_id, market, ticker, feature_version),
    CHECK (feature_cutoff_at <= t0)
);
```

`feature_cutoff_at <= t0`는 필수 제약이다. 각 특징의 실제 source 최대 시각도 lineage에서 검증하는 것이 바람직하다.

## 14. `reaction_labels`

`t0` 이후 실제 시장 반응을 라벨 버전별로 저장한다.

```sql
CREATE TABLE reaction_labels (
    news_id                         TEXT NOT NULL REFERENCES news_items(news_id),
    market                          TEXT NOT NULL,
    ticker                          TEXT NOT NULL,
    t0                              TIMESTAMPTZ NOT NULL,
    label_window_start              TIMESTAMPTZ NOT NULL,
    label_window_end                TIMESTAMPTZ NOT NULL,
    benchmark_id                    TEXT NOT NULL,
    future_max_return_30m           DOUBLE PRECISION,
    future_close_return_30m         DOUBLE PRECISION,
    future_max_excess_return_30m    DOUBLE PRECISION,
    future_turnover_z_30m           DOUBLE PRECISION,
    reaction_score                  DOUBLE PRECISION,
    reaction_class                  TEXT,
    is_strong_reaction              BOOLEAN,
    label_exclusion_reason          TEXT,
    label_version                   TEXT NOT NULL,
    generated_at                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (news_id, market, ticker, label_version),
    CHECK (label_window_start >= t0),
    CHECK (label_window_end > label_window_start),
    CHECK (reaction_class IS NULL OR reaction_class IN ('strong', 'medium', 'weak', 'none')),
    CHECK (
        (label_exclusion_reason IS NULL
            AND reaction_class IS NOT NULL
            AND is_strong_reaction IS NOT NULL)
        OR (label_exclusion_reason IS NOT NULL
            AND reaction_class IS NULL
            AND is_strong_reaction IS NULL)
    )
);
```

거래정지, 데이터 부족, 장 마감으로 30분 window를 만들 수 없는 경우 값을 임의 보간하지 않는다. `label_exclusion_reason`을 남기고 class·target을 NULL로 유지해 정상 negative와 구분한다.

## 15. 데이터셋 버전과 split

### 15.1 `dataset_versions`

```sql
CREATE TABLE dataset_versions (
    dataset_version    TEXT PRIMARY KEY,
    description        TEXT NOT NULL,
    train_start        TIMESTAMPTZ NOT NULL,
    train_end          TIMESTAMPTZ NOT NULL,
    valid_end          TIMESTAMPTZ NOT NULL,
    test_end           TIMESTAMPTZ NOT NULL,
    taxonomy_version   TEXT NOT NULL,
    trigger_model_version TEXT NOT NULL,
    trigger_prompt_version TEXT NOT NULL,
    extractor_version  TEXT NOT NULL,
    cluster_version    TEXT NOT NULL,
    mapping_version    TEXT NOT NULL,
    candidate_version  TEXT NOT NULL,
    feature_version    TEXT NOT NULL,
    label_version      TEXT NOT NULL,
    config             JSONB NOT NULL,
    source_snapshot    JSONB NOT NULL,
    manifest_checksum  TEXT NOT NULL,
    source_revision    TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (train_start < train_end),
    CHECK (train_end < valid_end),
    CHECK (valid_end < test_end)
);
```

### 15.2 `dataset_members`

```sql
CREATE TABLE dataset_members (
    dataset_version   TEXT NOT NULL REFERENCES dataset_versions(dataset_version),
    news_id           TEXT NOT NULL REFERENCES news_items(news_id),
    market            TEXT NOT NULL,
    ticker            TEXT NOT NULL,
    t0                TIMESTAMPTZ NOT NULL,
    split             TEXT NOT NULL,
    sample_weight     DOUBLE PRECISION NOT NULL DEFAULT 1.0,
    included          BOOLEAN NOT NULL,
    exclusion_reason  TEXT,
    PRIMARY KEY (dataset_version, news_id, market, ticker),
    CHECK (split IN ('train', 'valid', 'test')),
    CHECK (sample_weight > 0)
);
```

### Split 정책

- 시간 순서 train → valid → test
- 동일 `duplicate_cluster_id`와 `event_cluster_id`는 동일 split
- 동일 뉴스의 모든 후보는 동일 split
- scaler, clipping, category encoding은 train에서만 적합
- test 구간은 최종 1회 평가 전까지 잠금

예시 기간은 데이터 확보 상황에 따라 정하되 문서의 날짜를 그대로 상수화하지 않는다.

## 16. `training_pairs`

모델 입력용 비정규화 snapshot이다. 원천 테이블을 대체하지 않는다.

```sql
CREATE TABLE training_pairs (
    dataset_version                 TEXT NOT NULL,
    news_id                         TEXT NOT NULL,
    market                          TEXT NOT NULL,
    ticker                          TEXT NOT NULL,
    t0                              TIMESTAMPTZ NOT NULL,
    split                           TEXT NOT NULL,
    event_type                      TEXT NOT NULL,
    polarity                        TEXT NOT NULL,
    certainty                       TEXT NOT NULL,
    immediacy                       TEXT NOT NULL,
    scope                           TEXT NOT NULL,
    trigger_probability             DOUBLE PRECISION,
    relation_type                   TEXT NOT NULL,
    candidate_score                 DOUBLE PRECISION NOT NULL,
    direct_mention                  BOOLEAN NOT NULL,
    title_mention                   BOOLEAN NOT NULL,
    theme_match_score               DOUBLE PRECISION,
    sector_match_score              DOUBLE PRECISION,
    return_1m                       DOUBLE PRECISION,
    return_5m                       DOUBLE PRECISION,
    return_15m                      DOUBLE PRECISION,
    turnover_z_5m                   DOUBLE PRECISION,
    turnover_ratio_5m               DOUBLE PRECISION,
    volume_z_5m                     DOUBLE PRECISION,
    volatility_5m                   DOUBLE PRECISION,
    market_return_5m                DOUBLE PRECISION,
    sector_return_5m                DOUBLE PRECISION,
    sector_turnover_z_5m            DOUBLE PRECISION,
    avg_turnover_20d                NUMERIC,
    market_cap                      NUMERIC,
    minutes_from_open               INTEGER,
    session_type                    TEXT NOT NULL,
    session_bucket                  TEXT,
    pre_move_flag                   BOOLEAN NOT NULL,
    liquidity_pass                  BOOLEAN NOT NULL,
    future_max_excess_return_30m    DOUBLE PRECISION,
    future_turnover_z_30m           DOUBLE PRECISION,
    reaction_score                  DOUBLE PRECISION,
    reaction_class                  TEXT NOT NULL,
    is_strong_reaction              BOOLEAN NOT NULL,
    sample_weight                   DOUBLE PRECISION NOT NULL,
    taxonomy_version                TEXT NOT NULL,
    trigger_model_version           TEXT NOT NULL,
    trigger_prompt_version          TEXT NOT NULL,
    extractor_version               TEXT NOT NULL,
    cluster_version                 TEXT NOT NULL,
    mapping_version                 TEXT NOT NULL,
    candidate_version               TEXT NOT NULL,
    feature_version                 TEXT NOT NULL,
    label_version                   TEXT NOT NULL,
    created_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dataset_version, news_id, market, ticker)
);
```

민감한 원문 텍스트와 URL은 기본 학습 snapshot에 포함하지 않는다. 텍스트 임베딩을 사용할 경우 임베딩 값과 `embedding_model_version`을 별도 feature artifact로 관리한다.

## 17. 학습 데이터 생성 절차

1. `news_items`에 최초 관측시각을 보존해 적재
2. 중복·사건 cluster 생성
3. 버전된 `news_events`와 `news_entities` 생성
4. 기사 시점에 유효한 매핑으로 `news_candidates` 생성
5. 각 후보의 `t0` 이전 `market_features` 생성
6. 완결된 미래 window에서 `reaction_labels` 생성
7. cluster 단위 시간 split과 exclusion 적용
8. `dataset_versions`와 `dataset_members` 고정
9. `training_pairs` snapshot 생성
10. 행 수, class 분포, 결측, 누수, checksum 보고서 저장

## 18. 데이터 품질 게이트

| 검사 | 실패 조건 |
|---|---|
| 시간 누수 | `feature_cutoff_at > t0` 또는 source 최대 시각이 `t0` 초과 |
| 최초 관측 보존 | 재수집 후 `first_seen_at` 변경 |
| Split 누수 | 동일 duplicate/event cluster가 여러 split에 존재 |
| 후보 일관성 | 동일 candidate version에서 중복 `(news, market, ticker)` |
| 매핑 시점 | `t0`에 유효하지 않은 entity/theme mapping 사용 |
| 라벨 완결성 | window 부족인데 정상 라벨 생성 |
| 버전 누락 | 파생 행의 필수 version이 비어 있음 |
| 범위 오류 | 확률·confidence가 0~1 범위 밖 |
| 클래스 급변 | 이전 dataset 대비 class 비율이 허용 범위 초과 |
| 재현 실패 | 동일 source snapshot과 config의 checksum 불일치 |

## 19. MVP 최소 물리 범위

MVP에서 새로 필요한 뉴스 지능 테이블은 다음 9개다.

1. `news_items`
2. `news_events`
3. `news_clusters`
4. `news_entities`
5. `news_candidates`
6. `market_features`
7. `reaction_labels`
8. `dataset_versions`
9. `dataset_members`

`training_pairs`는 view 또는 export artifact로 시작할 수 있다. 동일 사건의 split 격리에 필요한 `news_clusters`는 MVP 필수다. 시점 매핑 테이블은 공통 종목 마스터가 동일 계약을 제공하면 별도 복제하지 않고 외부 source와 version만 참조한다.

`training_pairs`에는 `dataset_members.included = true`이고 exclusion 없는 완결 라벨만 포함한다. 제외 sample은 `dataset_members`와 `reaction_labels`에 사유를 남기되 학습 target으로 변환하지 않는다.

## 20. 한 행 예시

```json
{
  "dataset_version": "news-reaction-ds-v1",
  "news_id": "N20260619_001",
  "market": "KOSPI",
  "ticker": "000660",
  "t0": "2026-06-19T10:05:00+09:00",
  "split": "train",
  "event_type": "contract_supply",
  "polarity": "positive",
  "certainty": "C2",
  "immediacy": "I3",
  "trigger_probability": 0.84,
  "relation_type": "theme_related",
  "candidate_score": 0.91,
  "return_5m": 0.004,
  "turnover_z_5m": 1.8,
  "sector_return_5m": 0.006,
  "minutes_from_open": 35,
  "future_max_excess_return_30m": 0.032,
  "future_turnover_z_30m": 2.7,
  "reaction_class": "strong",
  "is_strong_reaction": true,
  "feature_version": "market-features-v1",
  "label_version": "reaction-30m-v1"
}
```

## 21. 완료 기준

1. DDL migration과 애플리케이션 DTO의 계약 테스트가 있다.
2. 모든 파생 테이블이 생성 버전과 기준 시각을 보존한다.
3. 미래 데이터와 split cluster 누수 검사가 자동화된다.
4. 동일 source snapshot과 config로 dataset checksum을 재현한다.
5. 제외된 샘플 수와 사유, class·이벤트·세션 분포를 데이터셋 보고서에 포함한다.
6. 공통 market 계층의 종목·시세 source와 뉴스 지능 테이블의 소유권이 중복되지 않는다.

한 줄로 요약하면, `training_pairs`는 모델 학습용 결과물이고 나머지 테이블과 version metadata는 그 결과물을 재현하는 근거다.
