# FinLabs News Intelligence 데이터·구조 마이그레이션 계획

> 현재 `modules/news`의 수집 자산을 보존하면서 News Intelligence의 시점·버전·학습 계약으로 안전하게 전환하기 위한 expand–backfill–cutover–cleanup 계획

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 계획 상태 | News Intelligence MVP 전환안 — 실제 migration 미구현 |
| 목표 데이터 모델 | [Training Data Model](./TrainDataTable.md) |
| 인터페이스 계약 | [Python Interface](./Interface.md) |
| 실행 백로그 | [Implementation Backlog](./Tasks.md) |
| 기준 시각 | `t0 = first_seen_at` |
| 기본 전략 | 기존 경로 유지 → 병행 기록 → 검증 → 읽기 전환 → 구형 구조 제거 |
| 중단 조건 | first-seen 손상, row loss, checksum 불일치, point-in-time 위반 |

## 1. 목적

이 문서는 실행 가능한 단일 SQL 파일이 아니다. 현재 뉴스 수집 파이프라인과 향후 학습·백테스트 데이터 모델 사이의 전환 순서, 안전장치, 검증 및 rollback 기준을 정의한다.

마이그레이션의 목표는 다음과 같다.

1. 기존 RSS·네이버 검색·entity·taxonomy 자산을 중단 없이 재사용한다.
2. 기존 `rss_items.created_at`·수집 실행 이력을 immutable `first_seen_at` 계약으로 전환한다.
3. 원천 뉴스, 파생 이벤트, 후보, feature, label, dataset snapshot을 분리한다.
4. 현재 DuckDB 중심 로컬 운영과 선택적 PostgreSQL mirror의 책임을 혼용하지 않는다.
5. 모든 전환 단계를 재실행 가능하고 rollback 가능하게 만든다.

## 2. 현재 상태와 목표 상태

### 2.1 현재 확인된 자산

| 영역 | 현재 상태 | 보존해야 할 가치 |
|---|---|---|
| RSS 수집 | `modules/news`에 parser·pipeline·DuckDB 적재 구현 | 표준화, 결정적 ID, 멱등 실행 |
| 네이버 검색 | `modules.news.naver.NaverNewsClient` 구현 | 키워드·날짜 검색, 완전성 검사, 공개 오류 계약 |
| Entity | 종목 마스터 기반 결정적 추출 구현 | 긴 이름 우선, confidence, 테스트 fixture |
| Event taxonomy | `modules/news/schema/event.py`의 taxonomy v1 DTO | 닫힌 event type, version validation |
| 뉴스 저장 | 모듈 내부 DuckDB schema와 pipeline 결합 | 기존 데이터와 운영 이력 |
| 공통 시장 데이터 | `modules/domain`, `modules/storage`, `modules/orchestration` 일부 구현 | broker-agnostic 시세·조회 경계 |
| Intelligence 학습 경로 | 미구현 | 새 계약에 따라 단계적으로 추가 |

### 2.2 목표 상태

```text
Provider 결과
    ↓ normalize
news_items ──────────────┬───────────────┐
    ↓                    ↓               │
news_clusters       news_events          │
                         ↓               │
                   news_entities         │
                         ↓               │
                  news_candidates        │
                         ↓               │
공통 시장 데이터 → market_features      │
                         ↓               ↓
                   reaction_labels       │
                         └──────┬────────┘
                                ↓
                        dataset_members
                                ↓
                       model / backtest
```

원천과 파생 테이블을 분리하고 모든 파생 행에 생성 version을 기록한다. `training_pairs`는 source of truth가 아니라 재생성 가능한 snapshot 또는 export artifact다.

## 3. 저장소 선택과 책임

FinLabs의 primary warehouse는 DuckDB다. SQLite는 운영 로그에만 사용하며 PostgreSQL/Supabase는 선택적 mirror다.

이 계획은 News Intelligence MVP의 현재 로컬 저장소 전환 범위다. 루트 `PLAN.md`의 PostgreSQL/TimescaleDB·Redis·Parquet 구조는 별도 장기 플랫폼 제안이며 MVP의 선행조건이 아니다. 그 플랫폼을 실제 채택하면 DuckDB↔PostgreSQL dual-write를 추가하지 않고 승인된 export/import 또는 신규 적재 절차를 별도 설계한다.

| 저장소 | 책임 | 마이그레이션 원칙 |
|---|---|---|
| DuckDB | 로컬 원천·파생 데이터와 분석 warehouse | MVP primary, schema migration 적용 대상 |
| SQLite | 실행 이력·오류 등 operational log | 시장·학습 데이터 저장 금지 |
| PostgreSQL/Supabase | 선택적 공유·mirror | primary 전환으로 간주하지 않으며 별도 승인 필요 |

[Training Data Model](./TrainDataTable.md)의 SQL은 데이터 계약을 설명하는 설계 초안이다. 실제 migration은 DuckDB 문법·제약과 프로젝트 migration 도구에 맞춰 작성한다. PostgreSQL mirror가 필요하면 동일 논리 계약을 별도 DDL로 관리하고 dual-primary 구조를 만들지 않는다.

## 4. 마이그레이션 원칙

1. **Expand before contract**: 새 column·table을 먼저 추가하고 구형 구조는 cutover 후 제거한다.
2. **Immutable first-seen**: 최초 관측값을 추론해 쓸 때 근거와 confidence를 보존하고 이후 덮어쓰지 않는다.
3. **Idempotent batches**: 모든 backfill은 범위·version·checkpoint로 재실행 가능해야 한다.
4. **No silent coercion**: 모르는 값은 NULL과 migration issue로 남기며 임의 기본값을 넣지 않는다.
5. **Point-in-time**: 현재 종목명·섹터·테마를 과거 기사에 무조건 소급하지 않는다.
6. **Versioned derivation**: 파생값 변경은 update-in-place가 아니라 새 version으로 생성한다.
7. **Observable cutover**: 새·구 경로의 row count, key set, checksum과 지연을 비교한 뒤 읽기를 전환한다.
8. **Reversible cleanup**: 구형 구조 삭제는 rollback window와 backup 검증 후 별도 migration으로 수행한다.

## 5. 식별자·시간 변환 계약

### 5.1 뉴스 식별자

목표 식별자는 `news_id`다. 기존 RSS ID와 네이버 결과를 하나의 값으로 억지 병합하지 않는다.

```text
news_id = deterministic(provider, provider_item_key or canonical_url)
```

- 기존 stable ID는 가능한 한 유지한다.
- ID 규칙 변경 시 `legacy_news_id_map(old_id, news_id, mapping_version)`을 생성한다.
- canonical URL 변경만으로 새 뉴스가 생성되지 않도록 provider key와 정규화 규칙을 기록한다.
- 충돌은 자동 overwrite하지 않고 quarantine table 또는 issue log로 보낸다.

### 5.2 `first_seen_at`

```text
t0 = first_seen_at
```

Backfill 우선순위는 다음과 같다.

1. 기존 `rss_items.created_at` 또는 ingest 실행에서 확인 가능한 최초 저장 시각
2. 동일 logical news의 여러 관측 기록 중 최소 저장 시각
3. 그 외에는 근거가 있는 legacy 수집 시각을 대체값으로 사용하고 `first_seen_source`에 원천 field를 기록

`published_at`을 `first_seen_at`으로 복사하지 않는다. 과거에 시스템이 실제로 관측했음을 증명할 수 없기 때문이다.

### 5.3 timezone

- 저장·비교 시 timezone-aware timestamp만 허용한다.
- 원본 offset이 있는 네이버 `pubDate`는 offset을 보존해 파싱한다.
- naive legacy timestamp는 기존 pipeline의 명시된 timezone 근거가 있을 때만 변환한다.
- 근거가 없으면 migration을 중단하고 issue로 분리한다.

## 6. 명칭·필드 변환

| 구형 개념 | 목표 개념 | 처리 |
|---|---|---|
| `rss_items` | `news_items` | 현재 RSS metadata와 네이버 검색 결과를 canonical metadata로 전환 |
| `articles.content` | 선택적 legacy text artifact | 기존 합법적 저장분만 보존하고 네이버 기사 전문을 생성·수집하지 않음 |
| `event_type_lvl1` | `event_type` | taxonomy v1 mapping 후 자유 문자열 거부 |
| `trigger_score` | `trigger_probability` 또는 `trigger_rule_score` | 확률 calibration 여부에 따라 분리 |
| `classifier_version` | `model_version` + `taxonomy_version` | 분류 모델과 taxonomy 독립 추적 |
| `generator_version` | `candidate_version` | 후보 산식·mapping version과 함께 보존 |
| `novelty` 문자열 | `novelty_score` | 근거가 없으면 NULL, 임의 숫자 변환 금지 |
| 단일 `ticker` key | `(market, ticker)` | 시장을 복합 식별자에 포함 |
| `is_active` 관계 | `valid_from`, `valid_to` | 과거 시점 재현 가능하게 변경 |
| `created_at`만 존재 | 기준 시각 + 생성 시각 | event time과 processing time 분리 |

구형 field를 삭제하기 전에 compatibility view 또는 mapper로 읽기 경로를 유지한다.

## 7. 단계별 실행 계획

### Phase 0 — Inventory와 backup

**작업**

- 실제 DuckDB schema, row count, key uniqueness, NULL 분포를 snapshot한다.
- DB 파일과 migration metadata를 backup하고 restore smoke test를 수행한다.
- current pipeline이 읽고 쓰는 table·column을 코드 검색으로 확정한다.
- schema version table이 없다면 먼저 추가한다.

**종료 조건**

- backup checksum과 restore 결과가 기록되어 있다.
- 모든 writer와 reader의 소유자가 식별되어 있다.
- 예상하지 못한 duplicate key와 naive timestamp 수가 보고되어 있다.

### Phase 1 — Expand schema

구형 table을 변경하지 않고 다음 구조를 추가한다.

- `news_items`
- `news_clusters`
- 버전된 `news_events`, `news_entities`, `news_candidates`
- `market_features`, `reaction_labels`
- `dataset_versions`, `dataset_members`
- migration run·issue·checkpoint metadata

필수 제약은 [Training Data Model](./TrainDataTable.md)을 따르되 DuckDB가 지원하지 않는 제약은 write transaction과 검증 query로 보완한다.

**종료 조건**: empty DB와 legacy fixture DB 모두에 expand migration이 성공하고 두 번째 실행은 no-op이다.

### Phase 2 — Canonical news backfill

1. legacy row를 provider별 canonical mapper로 변환한다.
2. `news_id`, canonical URL, text hash와 `first_seen_at`을 계산한다.
3. batch 단위 transaction으로 `news_items`에 insert한다.
4. old→new key mapping과 issue를 기록한다.
5. batch checkpoint를 commit 후 갱신한다.

**검증**

- source별 input count = migrated + skipped-known + quarantined
- key set과 canonical URL collision 보고
- `first_seen_at <= collected_at`; legacy `created_at` 변환 근거 포함
- `published_at`과 `first_seen_at` 차이 분포

### Phase 3 — Dual-write와 비교

새 수집부터 일정 기간 동일한 승인된 local primary 안에서 구형 table과 `news_items`에 병행 기록한다. 이 단계는 schema compatibility 검증용이며 DuckDB와 PostgreSQL을 dual-primary로 만드는 절차가 아니다. dual-write는 orchestration transaction에서 수행하며 한쪽만 성공하면 전체 operation을 실패 처리하거나 재처리 가능한 outbox를 남긴다.

비교 항목:

- logical news key 일치율
- title·description·URL checksum
- `first_seen_at` 불변성
- 저장 지연과 오류율
- source별 누락·중복률

**중단 조건**: silent partial write, first-seen 변경, key collision 증가 또는 허용치를 넘는 지연.

### Phase 4 — Derived data backfill

순서는 반드시 다음과 같다.

```text
clusters
→ events
→ entities
→ point-in-time mappings
→ candidates
→ market_features
→ reaction_labels
→ dataset_members
```

- 각 단계는 upstream version과 source checksum을 입력으로 받는다.
- 파생 실패는 원천 뉴스를 rollback하지 않고 issue와 exclusion reason을 남긴다.
- feature와 label을 같은 함수 또는 transaction에서 생성하지 않는다.
- feature backfill 완료 후에만 label backfill을 시작해 누수 검사를 단순화한다.

### Phase 5 — Read cutover

reader를 한 번에 모두 바꾸지 않고 다음 순서로 전환한다.

1. 검증용 query·report
2. dataset builder
3. model training·backtest
4. 운영 Top-K read API
5. legacy CLI/report reader

각 reader는 feature flag 또는 명시적 schema version으로 구·신 경로를 선택할 수 있어야 한다. 새 경로 결과가 acceptance criteria를 만족하면 default를 전환한다.

### Phase 6 — Writer cutover

- 새 canonical writer를 단일 write path로 전환한다.
- 구형 writer는 read-only로 잠그거나 호출 시 실패하게 한다.
- dual-write를 종료한 시각과 마지막 legacy key를 기록한다.
- rollback window 동안 compatibility view와 old table을 유지한다.

### Phase 7 — Contract와 cleanup

다음 조건을 모두 만족한 후 별도 migration에서 수행한다.

- rollback window 종료
- old reader 호출 0건
- 새 schema backup·restore 검증
- model·backtest 재현 성공
- 사용자 승인 또는 release gate 통과

그 후 구형 table·column·index·compatibility mapper를 제거한다. cleanup migration은 expand/cutover와 같은 배포에 포함하지 않는다.

## 8. Migration metadata

최소한 다음 실행 정보를 남긴다.

### `schema_migrations`

| 필드 | 설명 |
|---|---|
| `migration_id` | 정렬 가능한 고유 ID |
| `checksum` | migration 내용 checksum |
| `applied_at` | 적용 완료 시각 |
| `app_revision` | 적용 코드 revision |
| `duration_ms` | 실행 시간 |
| `status` | `running`, `succeeded`, `failed` |

### `data_migration_runs`

| 필드 | 설명 |
|---|---|
| `run_id`, `migration_name` | 실행 식별 |
| `source_schema_version`, `target_schema_version` | 전환 범위 |
| `range_start`, `range_end` | 처리 범위 |
| `last_checkpoint` | 재시작 위치 |
| `read_count`, `write_count`, `skip_count`, `error_count` | 수량 보존 |
| `config_json`, `source_revision` | 재현 정보 |
| `started_at`, `completed_at`, `status` | 감사 정보 |

### `data_migration_issues`

민감한 원문·credential을 저장하지 않는다. record key, issue code, 제한된 설명, retry 가능 여부와 해결 상태만 기록한다.

## 9. Transaction·locking·성능

- schema DDL과 대규모 backfill을 하나의 장시간 transaction으로 묶지 않는다.
- DuckDB single-writer 제약을 존중하고 기존 pipeline lock을 재사용한다.
- batch는 commit 가능한 크기로 제한하고 메모리·DB 파일 증가량을 관찰한다.
- index 또는 정렬 구조는 backfill access pattern을 근거로 추가한다.
- 대규모 derived backfill은 원천 ingestion과 시간대를 분리한다.
- `VACUUM`, file replacement 등 복구 비용이 큰 작업은 cleanup 단계에서 별도 수행한다.

## 10. 검증 query 계약

각 phase는 최소 다음 invariant를 검사한다.

| 영역 | invariant |
|---|---|
| 뉴스 | provider canonical key당 logical row 하나 |
| 시간 | `first_seen_at` non-null, timezone-aware, 재실행 시 불변 |
| 후보 | `(news_id, market, ticker, candidate_version)` unique |
| Feature | `feature_cutoff_at <= t0` |
| Label | `label_window_start >= t0`, end > start |
| Dataset | 동일 뉴스·cluster가 하나의 split에만 존재 |
| Version | 모든 파생 행의 version non-null |
| 수량 | source = migrated + known skip + quarantined |

표본 비교만으로 완료 판정하지 않는다. 전체 key set과 aggregate checksum을 비교하고, 사람이 읽는 sample review를 보조로 사용한다.

## 11. Rollback 계획

### Expand·backfill 단계

- 새 table·row를 사용하지 않으므로 기존 reader는 영향받지 않는다.
- 실패한 run의 target version row만 삭제하거나 새 run ID로 덮어쓴다.
- 원천 legacy row는 수정하지 않는다.

### Read cutover 단계

- feature flag 또는 schema version을 이전 reader로 되돌린다.
- cutover 이후 작성된 canonical row는 보존해 원인을 분석한다.

### Writer cutover 단계

- rollback은 compatibility writer가 검증된 rollback window 안에서만 허용한다.
- 새 경로 전용 데이터의 역변환 가능성을 사전에 시험한다.
- first-seen을 잃을 수 있는 rollback은 금지하고 canonical 값을 별도 보존한다.

### Rollback 불가 작업

old table 삭제, column 재사용, irreversible file compaction은 backup restore 외에 즉시 rollback이 어렵다. 반드시 Phase 7의 별도 승인 대상으로 둔다.

## 12. 실패 처리와 재시작

- process crash 후 마지막 commit된 checkpoint부터 재시작한다.
- 동일 `run_id`의 중복 실행을 lock 또는 unique constraint로 차단한다.
- 결정적 변환 오류는 retry loop에 넣지 않고 quarantine한다.
- 일시적 I/O 오류만 bounded retry한다.
- 부분 결과를 성공으로 표시하지 않는다.
- run 실패가 원천 수집 데이터를 삭제하거나 수정하지 않게 한다.

## 13. 보안·운영 고려사항

- DB backup과 migration log에 API credential을 포함하지 않는다.
- 기사 전문을 새 schema 채우기 목적으로 scraping하지 않는다.
- 사용자 로컬 DB 경로와 개인 계정 정보는 문서·fixture에 넣지 않는다.
- 오류 메시지는 URL query, header, credential을 sanitize한다.
- 실제 운영 DB migration 전 fixture와 복사본에서 dry run·restore를 수행한다.

## 14. 배포 단위와 권장 순서

| Release | 내용 | rollback |
|---|---|---|
| R1 | metadata + expand schema | 새 schema 미사용 |
| R2 | canonical news backfill 도구 | version row 제거·재실행 |
| R3 | dual-write + comparison report | legacy-only write 복귀 |
| R4 | derived backfill + quality gates | version 단위 폐기 |
| R5 | reader cutover | feature flag 복귀 |
| R6 | writer cutover | 검증된 compatibility writer |
| R7 | legacy cleanup | backup restore만 가능 |

한 release에서 expand, cutover, cleanup을 동시에 수행하지 않는다.

## 15. 완료 기준

1. 기존 뉴스 key와 canonical key의 mapping이 완전하게 감사 가능하다.
2. 모든 canonical news에 근거 있는 immutable `first_seen_at`이 있다.
3. dual-write 기간의 누락·중복·checksum 차이가 허용 기준 이내다.
4. feature·label·dataset의 point-in-time 및 cluster split 검사가 통과한다.
5. 동일 migration config와 source snapshot으로 row key·checksum을 재현한다.
6. 새 reader·writer의 rollback 절차가 복사본 DB에서 검증된다.
7. legacy cleanup 이전에 old path 사용량이 0임을 확인한다.
8. primary DuckDB와 선택적 mirror의 소유권·동기화 방향이 명확하다.
