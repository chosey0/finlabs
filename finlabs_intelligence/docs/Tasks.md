# FinLabs News Intelligence 구현 백로그

> 기존 FinLabs 계층과 뉴스 모듈을 재사용해 30분 시장 반응 랭킹 MVP를 단계적으로 구현하기 위한 실행 계획

| 항목 | 내용 |
|---|---|
| 상위 문서 | [FinLabs News Intelligence](../README.md) |
| 백로그 상태 | Reviewed plan — 현재 완료 상태는 각 task 구현 시 갱신 |
| 설계 기준 | [News Trigger Layer](./NewsTriggerLayer.md), [Market Reaction Layer](./MarketReactionLayer.md) |
| 데이터 계약 | [Feature Dictionary](./FeatureDictionary.md), [Training Data Model](./TrainDataTable.md) |
| 평가 계약 | [Backtest](./Backtest.md) |
| 전환·API 계약 | [Migration](./Migration.md), [Python Interface](./Interface.md) |
| 기준 시각 | `t0 = first_seen_at` |
| MVP 출력 | 뉴스별 후보 Top-K, 보정 반응 확률, 주요 근거와 버전 |
| 완료 원칙 | 각 단계의 산출물·테스트·종료 조건을 충족한 뒤 다음 단계 진행 |

## 1. 목표와 범위

MVP는 다음 파이프라인을 하나의 재현 가능한 흐름으로 완성한다.

```text
네이버 뉴스 검색·적재
    ↓
first-seen 보존·중복 cluster
    ↓
이벤트 분류·Entity Linking
    ↓
후보 생성
    ↓
t0 이전 시장 Feature
    ↓
t0 이후 30분 Reaction Label
    ↓
시간 순서 Dataset
    ↓
Baseline·LightGBM
    ↓
Top-K Backtest·평가 보고서
```

새로운 독립 프로젝트 구조를 만들지 않는다. 뉴스 기능은 `modules/news/`를 중심으로 구현하고 공통 종목 마스터·시세·저장소·orchestration 계층을 재사용한다. 자동 주문, 기사 전문 scraping, 공급망 지식 그래프, 온라인 투자 추천은 MVP 범위 밖이다.

## 2. 작업 운영 규칙

### 2.1 상태와 우선순위

- 상태: `TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`
- 우선순위: `P0`은 MVP 필수, `P1`은 품질·운영 보강, `P2`는 후속 확장
- 한 task는 검증 가능한 산출물과 acceptance criteria를 가진다.
- 완료 증거는 테스트 명령, 데이터 품질 결과 또는 생성 artifact 경로로 남긴다.

### 2.2 공통 Definition of Done

모든 구현 task는 다음을 만족해야 한다.

1. public contract와 실패 동작이 문서 또는 DTO에 반영되어 있다.
2. point-in-time, idempotency, 결정적 ordering을 관련 테스트로 검증한다.
3. 새 파생 데이터에 생성기 또는 모델 version이 기록된다.
4. 실제 외부 API를 호출하지 않는 단위 테스트가 있다.
5. 관련 targeted test, 전체 test, Ruff와 architecture boundary 검사가 통과한다.
6. 비밀정보·원문 기사·로컬 DB가 저장소에 포함되지 않는다.

## 3. 단계별 마일스톤

| 단계 | 목표 | 종료 조건 |
|---|---|---|
| M0. 계약 고정 | DTO·taxonomy·시간·버전 계약 통일 | 문서와 schema 테스트 일치 |
| M1. 데이터 기반 | 뉴스 first-seen, cluster, 시점 매핑 | 동일 입력 재처리 결과 결정적 |
| M2. Trigger·Candidate | 이벤트와 후보 집합 생성 | class 지표와 Candidate Recall@K 보고 |
| M3. Feature·Label | 누수 없는 학습 원천 생성 | point-in-time·label window 검사 통과 |
| M4. Dataset·Model | 시간 순서 dataset과 baseline 학습 | 고정 test에서 모델·baseline 비교 가능 |
| M5. Backtest·Report | 거래 가능성·안정성 평가 | 재현 가능한 평가 manifest와 승인 보고서 |
| M6. Shadow 운영 | 지연·drift·실패 모니터링 | 오류 예산과 관찰 기간 충족 |

## 4. M0 — 계약과 현행 자산 정렬

### NI-001 `[P0]` 현행 구현 inventory 확정

**작업**

- `modules/news/`의 네이버 client, schema, entity, 저장 경계를 목록화한다.
- 공통 market·storage·orchestration에서 재사용할 인터페이스를 식별한다.
- 문서의 “현재 구현”과 실제 코드를 대조한다.

**산출물**: 구현 현황표, 재사용 경계, 미구현 목록

**종료 조건**: 문서에 존재하지 않는 명령·테이블·서비스를 구현 완료로 표시한 항목이 없다.

### NI-002 `[P0]` 공통 DTO와 식별자 계약

**작업**

- `news_id`, `(market, ticker)`, `first_seen_at`, `collected_at` 의미를 DTO로 고정한다.
- `taxonomy_version`, `trigger_model_version`, `extractor_version`, `cluster_version`, `mapping_version`, `candidate_version`, `feature_version`, `label_version`, `dataset_version` 필드를 정의한다.
- timezone-aware timestamp와 score 범위 validation을 추가한다.
- [Python Interface](./Interface.md)의 public DTO·Protocol과 실제 package export를 일치시킨다.

**의존성**: NI-001

**종료 조건**: 잘못된 taxonomy, naive datetime, 범위 밖 점수를 거부하는 계약 테스트가 통과한다.

### NI-003 `[P0]` taxonomy v1 정합화

**작업**

- `modules/news/schema/event.py`의 닫힌 event type을 단일 source of truth로 사용한다.
- 분류 규칙·문서·학습 column의 과거 명칭을 migration mapping으로 정리한다.
- `market_commentary`, `simple_mention`, `other`의 negative/보류 정책을 고정한다.

**종료 조건**: 모든 producer·consumer가 [News Trigger Layer](./NewsTriggerLayer.md)의 taxonomy v1만 사용한다.

## 5. M1 — 뉴스 적재와 시점 데이터 기반

### NI-101 `[P0]` 네이버 뉴스 수집 use case 연결

**작업**

- 기존 `modules.news.naver.NaverNewsClient`를 orchestration use case에서 호출한다.
- keyword·검색일·호출 설정·수집 결과를 감사 가능하게 기록한다.
- API credential은 환경 또는 사용자 config에서 읽고 로그에서 마스킹한다.
- pagination 실패 시 부분 성공을 완전한 검색 결과로 저장하지 않는다.

**산출물**: 검색·적재 use case, mock 기반 통합 테스트

**종료 조건**: 성공, 빈 결과, 인증 실패, rate limit, 중간 page 실패를 결정적으로 처리한다.

### NI-102 `[P0]` `news_items` 저장과 immutable first-seen

**작업**

- 제목, `description`, 링크, `published_at`, `first_seen_at`, `collected_at`을 저장한다.
- canonical URL과 정규화 text hash로 idempotent upsert를 구현한다.
- 재수집 시 `first_seen_at`이 변경되지 않도록 DB 제약 또는 원자적 upsert로 보장한다.

**의존성**: NI-002, NI-101

**종료 조건**: 같은 기사를 여러 번 적재해도 logical row와 `first_seen_at`이 동일하다.

### NI-103 `[P0]` duplicate·event cluster v1

**작업**

- canonical URL, 정규화 제목, entity, event type, 시간 근접도를 이용한다.
- `duplicate_cluster_id`, `event_cluster_id`, `is_cluster_primary`, `cluster_version`을 생성한다.
- 같은 cluster가 split 경계를 넘지 않게 dataset builder에서 강제한다.

**의존성**: NI-102, NI-203

**종료 조건**: 전재·반복 기사 fixture의 cluster 결과가 결정적이며 재실행 시 동일하다.

### NI-104 `[P0]` point-in-time 종목·관계 매핑

**작업**

- 공통 종목 마스터를 재사용해 회사명·별칭을 `(market, ticker)`로 연결한다.
- entity·theme·sector mapping에 `valid_from`, `valid_to`, `mapping_version`을 둔다.
- 과거 기사 재생성 시 현재 회사명·테마 관계가 소급 적용되지 않게 한다.

**종료 조건**: 회사명 변경·상장폐지·관계 변경 fixture에서 기사 시점의 mapping이 선택된다.

## 6. M2 — Trigger 분류와 후보 생성

### NI-201 `[P0]` 텍스트 정규화

**작업**

- 네이버가 제공하는 `title + description`만 모델 입력으로 사용한다.
- HTML entity와 검색 결과 강조 tag를 제거하고 공백을 정규화한다.
- 원문 본문이 없는 상태를 정상 입력으로 처리하며 scraping을 추가하지 않는다.

**의존성**: NI-102

**종료 조건**: 동일 의미의 markup 변형이 동일한 정규화 결과와 hash를 만든다.

### NI-202 `[P0]` Entity Linking v1

**작업**

- 제목·요약에서 기업명과 별칭을 추출한다.
- `title_mention`, 등장 횟수, match span, mapping 근거를 저장한다.
- 모호한 별칭은 강제 매핑하지 않고 unresolved entity로 남긴다.

**의존성**: NI-104, NI-201

**종료 조건**: 직접 언급, 별칭 충돌, 미매핑 entity fixture를 통과한다.

### NI-203 `[P0]` 규칙 기반 Trigger baseline

**작업**

- taxonomy v1 event type과 `polarity`, `certainty`, `immediacy`, `scope`를 생성한다.
- `trigger_probability`와 사후 `is_trigger` label을 물리적으로 분리한다.
- rule set과 threshold를 `extractor_version` 또는 `model_version`으로 보존한다.

**의존성**: NI-003, NI-201

**종료 조건**: class별 precision·recall, confusion matrix와 `other` 비율을 평가셋에서 보고한다.

### NI-204 `[P0]` Candidate Generation v1

**작업**

- `direct_mention`, `theme_related`, `sector_peer` 순으로 후보를 생성한다.
- relation reason과 적용된 mapping version을 후보마다 보존한다.
- 미래 반응과 유동성 점수를 `candidate_score` 산식에 넣지 않는다.
- 점수 동률 시 `(candidate_score DESC, market ASC, ticker ASC)`로 정렬한다.

**의존성**: NI-202, NI-203

**종료 조건**: Candidate Recall@5/10/20, 뉴스당 평균 후보 수, 관계 유형별 recall을 보고한다.

### NI-205 `[P1]` post-hoc·novelty 품질 보강

**작업**

- “급등 이유”, “상한가 배경” 등 문구와 가격 선행 조건을 결합한다.
- `is_posthoc_article`, `novelty_score`와 근거를 저장한다.
- 안정적 novelty가 없으면 기본값으로 채우지 않고 feature에서 제외한다.

**의존성**: NI-103, NI-203

## 7. M3 — Market Feature와 Reaction Label

### NI-301 `[P0]` point-in-time 1분봉 reader

**작업**

- 공통 OHLCV repository에서 종목·시장·섹터 series를 읽는다.
- 거래소 calendar, timezone, corporate action 보정을 통일한다.
- `t0` 이전 마지막 완결 bar와 source 최대 시각을 반환한다.

**종료 조건**: 분봉 중간 도착, 장 시작, 장 마감, 휴장일, bar 누락 fixture를 통과한다.

### NI-302 `[P0]` Feature Builder v1

**작업**

- [Feature Dictionary](./FeatureDictionary.md)의 MVP feature set을 구현한다.
- 모든 lookback을 `feature_cutoff_at <= t0`로 제한한다.
- z-score baseline은 sample 이전 완료 거래일과 동일 시간대 분포만 사용한다.
- 결측은 NULL과 `missing_flags`로 보존한다.

**의존성**: NI-204, NI-301

**종료 조건**: 미래 bar를 주입한 adversarial fixture에서도 feature 값이 변하지 않는다.

### NI-303 `[P0]` Reaction Label Generator v1

**작업**

- `label_window_start`, `label_window_end`, benchmark를 명시적으로 저장한다.
- 30분 최대 수익률, 최대 초과수익률, 종가 수익률, 거래대금 z-score를 계산한다.
- `reaction_class`와 `is_strong_reaction`을 `label_version` 규칙으로 생성한다.
- 장 마감·거래정지·데이터 부족은 보간하지 않고 exclusion reason을 남기며 class·target은 NULL로 유지한다.

**의존성**: NI-301

**종료 조건**: [Feature Dictionary](./FeatureDictionary.md)의 산식과 경계값 fixture가 일치한다.

### NI-304 `[P0]` 시간 누수 품질 게이트

**작업**

- 각 feature source의 최대 timestamp가 `t0` 이하인지 검사한다.
- label source가 feature export에 포함되지 않는지 schema allowlist로 검사한다.
- 장외 cohort와 장중 cohort를 분리한다.

**의존성**: NI-302, NI-303

**종료 조건**: 의도적으로 미래 값을 섞은 fixture가 pipeline을 실패시킨다.

## 8. M4 — Dataset과 모델

### NI-401 `[P0]` dataset manifest와 time split

**작업**

- source snapshot, taxonomy·Trigger model·extractor·cluster·mapping·candidate·feature·label version, 기간과 제외 규칙을 manifest로 고정한다.
- train → valid → test 시간 순서를 강제한다.
- 동일 뉴스와 duplicate/event cluster의 모든 후보를 하나의 split에 둔다.
- dataset checksum과 row count를 저장한다.

**의존성**: NI-103, NI-304

**종료 조건**: 동일 manifest 재실행의 member key와 checksum이 동일하다.

### NI-402 `[P0]` training pair export

**작업**

- 이벤트·후보·feature·label을 `(news_id, market, ticker)`로 결합한다.
- 모델 입력 column은 registry allowlist로 제한한다.
- 미래 수익률, label window, cluster ID와 exclusion reason을 입력에서 제거한다.
- encoder·imputer·scaler는 train split에서만 적합한다.

**의존성**: NI-401

**종료 조건**: [Training Data Model](./TrainDataTable.md)의 품질 게이트와 schema 검사가 통과한다.

### NI-403 `[P0]` ranking baseline suite

**작업**

- random, direct mention, `candidate_score`, `turnover_z_5m` baseline을 구현한다.
- 모든 baseline이 같은 후보·test·필터를 사용하게 한다.
- random baseline은 seed와 반복 횟수를 manifest에 저장한다.

**의존성**: NI-402

**종료 조건**: 반복 실행 결과가 seed 기준으로 재현되고 공통 평가 interface를 사용한다.

### NI-404 `[P0]` LightGBM binary baseline

**작업**

- target을 `is_strong_reaction`으로 고정한다.
- valid 구간에서 hyperparameter·class weight·early stopping을 결정한다.
- isotonic 또는 Platt calibration을 valid 구간에서만 적합한다.
- 모델, feature list, 전처리, calibration과 학습 manifest를 하나의 artifact로 등록한다.

**의존성**: NI-402

**종료 조건**: test를 학습·튜닝에 사용하지 않고 PR-AUC, Brier score, Hit@K를 산출한다.

### NI-405 `[P0]` 뉴스별 Ranking Engine

**작업**

- 같은 `news_id` 내 후보를 보정 확률로 정렬한다.
- 결정적 tie-breaker와 Top-K 응답 계약을 구현한다.
- model·feature·candidate version과 주요 기여 요약을 출력한다.

**의존성**: NI-404

## 9. M5 — Backtest와 승인 보고서

### NI-501 `[P0]` Ranking evaluation

**작업**

- Hit@1/3/5, Precision@K, NDCG@5/10, MRR을 구현한다.
- query group은 뉴스 단위로 유지하고 label 정의는 `label_version`을 재사용한다.
- candidate quality와 model ranking quality를 분리해 보고한다.

**의존성**: NI-403, NI-404

**종료 조건**: hand-calculated fixture와 지표 결과가 일치한다.

### NI-502 `[P0]` Tradable backtest runner

**작업**

- [Backtest](./Backtest.md)의 entry·exit·비용·체결 가능성 규칙을 구현한다.
- Ranking, Tradable, Conservative 시나리오를 분리한다.
- 뉴스별 평가와 chronological portfolio 평가를 각각 산출한다.
- 제외·미체결 사유와 `backtest_config`를 보존한다.

**의존성**: NI-301, NI-405, NI-501

**종료 조건**: 미래 고가를 체결 가격으로 쓰지 않으며 지연·비용 민감도 결과가 재현된다.

### NI-503 `[P0]` slice·불확실성 분석

**작업**

- 이벤트, relation, 시장, 유동성, 시간대, 월별 결과를 집계한다.
- event cluster 단위 bootstrap 신뢰구간을 계산한다.
- 최악 월, 최대 낙폭, 비용 손익분기점을 보고한다.

**의존성**: NI-502

### NI-504 `[P0]` MVP 승인 보고서

**작업**

- 모델과 baseline을 동일 test 조건에서 비교한다.
- 데이터 기간, 표본 수, 제외율, 가정, 신뢰구간과 known limitation을 명시한다.
- 승인·보류·재설계 중 하나의 결론과 근거를 기록한다.

**의존성**: NI-503

**종료 조건**: [README의 MVP 승인 기준](../README.md#6-mvp-승인-기준)을 모두 증거와 연결한다.

## 10. M6 — Shadow 운영과 관측성

### NI-601 `[P1]` batch·online parity

- 동일 feature registry와 변환 artifact를 학습·추론에서 공유한다.
- 대표 sample의 batch/online feature parity를 자동 비교한다.

### NI-602 `[P1]` 지연·실패 모니터링

- 수집 지연, 후보 생성·feature·추론 p50/p95, API 실패율을 수집한다.
- 부분 수집, mapping 실패, stale market data를 구분해 경보한다.

### NI-603 `[P1]` drift·calibration 모니터링

- feature 분포, event type 비율, 후보 수, 확률 calibration의 시간 변화를 추적한다.
- 재학습 trigger는 자동 배포가 아니라 검토 작업을 생성한다.

### NI-604 `[P1]` Top-K read API 또는 화면 연결

- 확률, `t0`, 주요 근거, warning, model/data version을 함께 표시한다.
- 분석 신호이며 투자 추천·수익 보장이 아님을 명시한다.

## 11. 후속 작업

| ID | 우선순위 | 작업 | 선행 조건 |
|---|---|---|---|
| NI-701 | P2 | pairwise 또는 LambdaRank 비교 | M5 승인 |
| NI-702 | P2 | 공급망·고객·경쟁사 관계 그래프 | mapping governance 확정 |
| NI-703 | P2 | 다중 horizon 5·15·60분 모델 | 30분 baseline 안정화 |
| NI-704 | P2 | 장외 전용 cohort 모델 | 장외 표본·체결 규칙 확보 |
| NI-705 | P2 | embedding 기반 event clustering | v1 cluster 평가 완료 |
| NI-706 | P2 | 해외 뉴스의 국내 종목 전이 | 별도 제품 범위 승인 |

새 의존성, 외부 모델 또는 vector store는 해당 task의 성능·운영상 필요성이 입증되고 명시적으로 승인된 뒤 도입한다.

## 12. 의존성 순서

```text
NI-001 → NI-002 ─┬→ NI-102 → NI-201 → NI-202 ─┐
                 └→ NI-003 → NI-203 ───────────┼→ NI-204
NI-101 ─────────────→ NI-102                    │
NI-104 ─────────────────────────→ NI-202 ───────┘

NI-204 + NI-301 → NI-302
NI-301          → NI-303
NI-302 + NI-303 → NI-304
NI-103 + NI-304 → NI-401 → NI-402
NI-402          → NI-403 + NI-404 → NI-405
NI-403 + NI-405 → NI-501 → NI-502 → NI-503 → NI-504
```

NI-103은 event type을 사용하는 정교한 cluster 단계에서 NI-203을 필요로 한다. 초기 URL·제목 중복 처리는 NI-102 직후 시작하고, event cluster는 Trigger 분류 후 완성한다.

## 13. MVP 범위 요약

### P0 — 반드시 완료

- immutable `first_seen_at`과 idempotent 뉴스 적재
- taxonomy v1, Entity Linking, 직접·테마·섹터 후보
- point-in-time market feature와 30분 label
- cluster 격리 time split과 dataset manifest
- 공통 baseline, LightGBM, calibration
- 랭킹·거래 가능성 백테스트와 승인 보고서

### P1 — MVP 품질·운영 보강

- post-hoc·novelty 품질 개선
- ranking response와 shadow 운영
- 지연·실패·drift·calibration 모니터링

### P2 — 승인 이후 확장

- 학습형 ranking, 관계 그래프, 다중 horizon, 장외·해외 뉴스 확장

## 14. MVP 완료 정의

다음 조건을 모두 충족해야 MVP를 완료로 표시한다.

1. 뉴스 검색부터 평가 보고서까지 하나의 dataset manifest로 추적된다.
2. 동일 입력·버전으로 후보, feature, label과 test 지표를 재현할 수 있다.
3. 미래 데이터, 재수집 시각 덮어쓰기, cluster split 누수 검사가 자동화되어 있다.
4. 모델과 최소 네 가지 baseline을 같은 시간 순서 test에서 비교한다.
5. Top-K 랭킹 지표, calibration, 비용 반영 수익률과 신뢰구간을 함께 보고한다.
6. 장외·장마감·저유동성·거래정지·결측·중복의 처리 사유가 데이터에 남는다.
7. 코드·데이터·모델·평가 config version이 결과와 함께 저장된다.
8. 문서와 실제 public contract가 일치하고 전체 검증 suite가 통과한다.
