# FinLabs News Intelligence

> 뉴스 이벤트를 구조화하고, 관련 종목의 단기 시장 반응 가능성을 순위화하기 위한 제품·데이터·모델 설계 문서


| 항목        | 내용                                     |
| --------- | -------------------------------------- |
| 문서 상태     | Reviewed target design — 구현 상태는 10절 참조 |
| 기준일       | 2026-06-20                             |
| 의사결정 단위   | 뉴스 1건 × 후보 종목 1개 × 관측 시각 `t0`          |
| MVP 예측 목표 | `t0` 이후 30분 내 강한 초과수익·거래대금 반응 여부       |
| 운영 출력     | 뉴스별 반응 가능 종목 Top-K와 주요 근거              |


## 1. Executive Summary

FinLabs News Intelligence는 “좋은 뉴스인가”를 판정하는 시스템이 아니라, **새로운 뉴스 이벤트가 어떤 종목에 연결되고 그 종목이 단기적으로 유의미한 시장 반응을 보일 가능성이 있는가**를 추정하는 시스템이다.

제품은 두 계층과 재현 가능한 데이터·평가 기반으로 구성한다. 이 폴더는 **목표 설계**이며, 현재 제공되는 public API와 완료된 기능은 [10절](#10-현재-구현과의-연결)에서 별도로 표시한다.

1. [News Trigger Layer](./docs/NewsTriggerLayer.md)는 뉴스 제목·요약을 이벤트, 확실성, 즉시성, 영향 범위와 후보 종목으로 구조화한다.
2. [Market Reaction Layer](./docs/MarketReactionLayer.md)는 뉴스 신호와 `t0` 이전 시장 상태를 결합해 후보 종목을 순위화한다.
3. [Feature Dictionary](./docs/FeatureDictionary.md)는 모델 입력과 라벨의 산식·시점·결측·버전 계약을 고정한다.
4. [Training Data Model](./docs/TrainDataTable.md)은 입력·특징·라벨·데이터셋 버전을 분리해 모든 학습 행을 재현 가능하게 만든다.
5. [Backtest](./docs/Backtest.md)는 랭킹 품질과 체결 기반 수익성을 분리해 baseline 대비 검증한다.
6. [Implementation Backlog](./docs/Tasks.md)는 기존 FinLabs 자산을 재사용하는 단계별 작업과 완료 조건을 정의한다.
7. [Migration](./docs/Migration.md)은 기존 뉴스 데이터와 write path를 중단 없이 새 계약으로 전환하는 절차를 정의한다.
8. [Python Interface](./docs/Interface.md)는 현재 `modules/` 계층을 따르는 DTO·Protocol·orchestration 경계를 고정한다.

```text
뉴스 제목·요약
    ↓
News Trigger Layer
    ├─ 이벤트 분류
    ├─ 종목 후보 생성
    └─ 뉴스 신호 산출
    ↓
Market Reaction Layer
    ├─ t0 이전 시장 특징 결합
    ├─ 반응 확률 추정
    └─ 뉴스별 Top-K 랭킹
    ↓
Backtest·평가 보고서
    ↓
알림·리서치·shadow 운영
```

## 2. Problem Statement

뉴스만으로 가격 반응을 설명하기 어렵다. 같은 계약 기사라도 이미 선반영됐거나, 유동성이 부족하거나, 시장 전체가 급락 중이면 반응이 제한될 수 있다. 반대로 직접 언급되지 않은 섹터·테마 종목이 더 크게 반응할 수 있다.

따라서 다음 두 문제를 분리한다.

- **Trigger 문제**: 이 뉴스가 가격에 영향을 줄 수 있는 새 이벤트인가? 어떤 종목과 어떤 관계인가?
- **Reaction 문제**: 현재 시장 상태에서 후보 종목 중 누가 가장 빠르고 강하게 반응할 가능성이 높은가?

## 3. Product Scope

### MVP 포함

- 네이버 뉴스 검색 API의 제목, `description`, 링크, 발행시각 사용
- 닫힌 이벤트 taxonomy와 버전 관리
- 직접 언급, 테마, 섹터 기반 후보 생성
- 1분봉 기반 가격·거래대금·시장·섹터 특징
- 뉴스별 후보의 30분 내 강한 반응 확률과 Top-K
- 시간 순서 기반 학습·검증·테스트 분리
- 모든 특징과 라벨의 point-in-time 재현성

### MVP 제외

- 언론사 원문 HTML 또는 기사 전문 수집
- 자동 주문과 포트폴리오 운용
- 공급망·고객사·경쟁사 전체 지식 그래프
- 해외 뉴스에서 국내 종목으로의 자동 전이
- 초단타 호가 기반 체결 전략
- 수익률을 보장하는 표현 또는 투자 추천

### 현재 구현과 목표 설계의 경계

- 현재 사용 가능: RSS pipeline, 네이버 키워드·날짜 검색 client, 종목 Entity 추출, taxonomy v1 DTO, FastAPI/React 기반 학습 데이터 수집·라벨링 MVP, annotation revision, reaction preview, dataset freeze/export
- 구현 중/후속 범위: canonical live news 적재, Trigger 분류 실행기, 후보 확장, full market feature builder, 모델 학습·registry, backtest, Top-K serving
- 문서의 JSON·Python·SQL 예시는 해당 절에서 “현재 구현”으로 명시하지 않는 한 target contract다.

## 4. 공통 데이터 계약

### 4.1 시간 기준


| 필드              | 정의                                   | 사용 목적                                |
| --------------- | ------------------------------------ | ------------------------------------ |
| `published_at`  | 뉴스 제공자가 표시한 발행시각                     | 출처 표시와 품질 점검                         |
| `first_seen_at` | FinLabs가 해당 뉴스를 처음 사용할 수 있게 된 시각     | 학습·백테스트 기준 시각 `t0`                   |
| `collected_at`  | canonical row가 가장 최근 성공적으로 저장·갱신된 시각 | 운영 최신성 확인; 실행별 이력은 ingestion run에 기록 |


`t0 = first_seen_at`을 원칙으로 한다. 발행시각이 더 이르더라도 시스템이 알 수 없었던 구간의 시장 데이터는 특징으로 사용하지 않는다. 같은 기사를 재수집해도 `first_seen_at`은 변경하지 않는다.

### 4.2 정보 가용성 원칙

- 모델 입력은 `t0` 시점에 이용 가능했던 값만 사용한다.
- 가격·거래대금 특징의 관측 구간은 `t0` 이하에서 끝나야 한다.
- 라벨 계산에 사용한 `t0` 이후 데이터는 특징 테이블에 포함하지 않는다.
- 종목명·별칭·섹터 매핑도 기사 시점에 유효했던 버전을 사용한다.
- 중복 기사 클러스터는 시간 분할 경계를 넘어가지 않도록 동일 split에 배치한다.

### 4.3 식별자와 버전

- 뉴스: `news_id`
- 후보 샘플: `(news_id, market, ticker, t0)`
- 재현 버전: `taxonomy_version`, `trigger_model_version`, `extractor_version`, `cluster_version`, `mapping_version`, `candidate_version`, `feature_version`, `label_version`, `dataset_version`

### 4.4 저장소와 문서 우선순위

- News Intelligence의 source of truth는 PostgreSQL(예: Supabase, RDS, 자체 호스팅)이며 표준 libpq 연결 문자열 `INTELLIGENCE_DATABASE_URL`로 접근한다. catalog(`domestic_symbols`)도 같은 DB에서 읽고, `scripts/load_kis_symbols_to_supabase.py`(KIS 직행) 또는 `scripts/seed_intelligence_catalog.py`(DuckDB 원본 → DB)로 적재한다.
- 뉴스 수집 pipeline(`modules/news`)은 현재 finlabs_intelligence와 같은 PostgreSQL 인스턴스를 사용한다. 과거 DuckDB/SQLite 뉴스 경로는 레거시로만 취급한다.
- 현재 뉴스 pipeline의 동작·명령은 [`modules/news/README.md`](../modules/news/README.md)를 따른다.
- 현재 모듈의 장기 작업은 [`modules/news/PLAN.md`](../modules/news/PLAN.md), News Intelligence의 목표 계약은 이 폴더의 문서를 따른다.
- 필드 의미는 [Feature Dictionary](./docs/FeatureDictionary.md), 물리·논리 데이터 구조는 [Training Data Model](./docs/TrainDataTable.md), 전환 순서는 [Migration](./docs/Migration.md)을 우선한다.

## 5. 성공 지표

### 오프라인 모델 지표

- Candidate Recall@K
- Hit@1, Hit@3, Hit@5
- NDCG@5, NDCG@10
- Precision@K와 False Positive Rate
- Top-K 평균 30분 초과수익률
- 확률 calibration: Brier score 또는 Expected Calibration Error

### 운영 지표

- 뉴스 수집 지연: `first_seen_at - published_at`
- 후보 생성 및 모델 추론 p95 지연
- 뉴스당 평균 후보 수
- API·분류·특징 생성 실패율
- 모델·데이터 버전별 재현 성공률

## 6. MVP 승인 기준

MVP는 다음 조건을 모두 만족할 때 완료로 판정한다.

1. 동일 원천 데이터와 버전으로 같은 학습 데이터셋을 재생성할 수 있다.
2. 시간 순서 테스트 구간에서 후보 Recall@K와 뉴스별 랭킹 지표를 보고한다.
3. 랜덤, 직접 언급 우선, 거래대금 모멘텀 등 단순 baseline과 비교한다.
4. 미래 데이터 누수 검사와 중복 기사 split 격리 검사를 자동화한다.
5. 뉴스가 없거나 불완전하거나 장외인 경우의 처리 규칙이 결정적이다.
6. 결과 화면은 확률, 기준 시각, 데이터 버전과 주요 근거를 함께 표시한다.

## 7. 주요 리스크와 대응


| 리스크                | 영향         | 대응                                       |
| ------------------ | ---------- | ---------------------------------------- |
| 발행시각과 실제 관측시각 차이   | 미래 정보 누수   | `first_seen_at`을 `t0`로 고정                |
| 네이버 API의 기사 전문 미제공 | 문맥 부족      | 제목+요약 계약을 명시하고 입력 품질 지표 관리               |
| 사후 원인 분석 기사        | 잘못된 인과 라벨  | post-hoc 탐지와 pre-move 검사                 |
| 전재·중복 기사           | 샘플 과대계상    | URL·제목·시간 및 콘텐츠 유사도 기반 클러스터              |
| 낮은 유동성             | 비현실적 반응 라벨 | 최소 거래대금·스프레드 필터                          |
| 시장 국면 변화           | 성능 저하      | 시간 순서 검증, rolling evaluation, drift 모니터링 |
| 확률의 투자 추천 오인       | 제품·규제 위험   | 분석 신호임을 명시하고 자동 주문과 분리                   |


## 8. 결정이 필요한 항목


| 항목           | MVP 제안                                                     | 확정 시점                |
| ------------ | ---------------------------------------------------------- | -------------------- |
| 반응 horizon   | 30분                                                        | 탐색 분석 후 5·15·60분과 비교 |
| 시장 benchmark | KOSPI/KOSDAQ 지수, 필요 시 섹터 지수                                | 라벨 실험 전              |
| 강한 반응 기준     | 30분 최대 초과수익률 3% 이상 + 거래대금 Z-score 2 이상                     | 분포 분석 후              |
| 장외 기사 라벨 시작  | `t0`는 유지하고 `label_window_start`를 다음 정규장으로 설정해 별도 cohort 처리 | 데이터 생성기 구현 전         |
| 최소 유동성       | 최근 20거래일 평균 거래대금 분위수 기준                                    | 학습 표본 분석 후           |
| Top-K        | 5                                                          | 운영 화면 설계 전           |


수치 임계값은 현재 가설이며, 코드 상수로 고정하기 전에 데이터 분포와 거래비용을 기준으로 버전 관리해야 한다.

## 9. 구현 로드맵


| 단계              | 핵심 산출물                                        | 종료 조건                            |
| --------------- | --------------------------------------------- | -------------------------------- |
| 0. 계약 고정        | 시간·식별자·taxonomy·버전 계약                         | DTO와 문서 필드 일치, 계약 테스트 통과         |
| 1. 데이터 기반       | 뉴스 적재, first-seen 보존, 시점 매핑, dataset manifest | 동일 입력의 dataset checksum 재현       |
| 2. Trigger MVP  | 이벤트 분류, entity 추출, 직접·테마·섹터 후보                | class별 F1과 Candidate Recall@K 보고 |
| 3. Reaction MVP | point-in-time 특징, 30분 라벨, baseline, LightGBM  | 시간 순서 test에서 baseline 비교 완료      |
| 4. 운영 검증        | Top-K API·화면, 지연·drift·실패 모니터링                | shadow 운영 기간과 오류 예산 충족           |
| 5. 고도화          | pairwise/listwise ranking, 관계 그래프, 다중 horizon | MVP 대비 개선의 통계적·경제적 유의성 확인        |


세부 작업의 의존성, 우선순위와 단계별 종료 조건은 [Implementation Backlog](./docs/Tasks.md), 평가 시각·체결·비용·포트폴리오 가정은 [Backtest](./docs/Backtest.md)를 따른다. 기존 데이터와 실행 경로의 전환은 [Migration](./docs/Migration.md), Python 경계는 [Python Interface](./docs/Interface.md)를 기준으로 한다.

## 10. 현재 구현과의 연결


| 영역       | 현재 자산                                              | 남은 작업                                           |
| -------- | -------------------------------------------------- | ----------------------------------------------- |
| 뉴스 수집·검색 | RSS pipeline과 `modules.news.naver.NaverNewsClient` | 네이버 결과의 canonical live 저장·백필·호출 예산·체크포인트 연결          |
| 이벤트 계약   | `modules/news/schema/event.py` taxonomy v1과 DTO    | 실제 분류 실행기, 평가셋, 버전별 재분류                         |
| Entity   | 저장된 승인 텍스트 대상 종목명·소규모 별칭 기반 추출                      | 제목+요약 입력 연결, point-in-time 별칭과 산업·키워드 확장        |
| 급등 사건    | 공통 market 계층의 `SurgeEvent` 추출·저장                   | 뉴스 학습 라벨·사례 생성과 연결                              |
| 시세 특징    | Kiwoom 1분봉 기반 차트 로딩과 30거래분 reaction preview               | full point-in-time feature builder                |
| 데이터셋    | annotation revision 기반 dataset freeze와 DB·JSON·CSV export | 모델 학습용 feature table 확장                      |
| 모델       | 초기 학습 스크립트와 metric primitive                         | baseline, LightGBM, calibration, model registry |


기존 pipeline의 구현 상태와 운영 명령은 [`modules/news/README.md`](../modules/news/README.md), 기존 모듈의 장기 계획은 [`modules/news/PLAN.md`](../modules/news/PLAN.md)를 따른다. 이 폴더는 그 위에 추가할 뉴스 지능 계층의 제품·데이터·모델·평가 계약을 설명한다.

## 11. 학습 데이터 수집 웹 도구

현재 구현된 로컬 MVP는 KIS `domestic_symbols` 스냅샷 검색, Kiwoom 주식 1분봉과 `ka20005` KOSPI/KOSDAQ 벤치마크 조회, 캔들 선택 또는 뉴스 검색 구간(시작·끝=t0) 직접 입력, Naver의 정확한 뉴스 구간 검색(기본 직전 1시간, 시작 시각은 직접 조정 가능), 차트의 t0 기준 30거래분 반응 윈도 음영과 거래량·거래대금 보조지표(토스 레퍼런스), 직접 언급 제안, 사람의 append-only 라벨 수정, 30거래분 반응 preview, 버전 스냅샷과 PostgreSQL(DB)·JSON·CSV 출력을 제공한다. 검색 결과는 서버가 발급한 안정적인 `sample_id`로 저장되며 라벨은 종목-기사-유효 라벨 anchor 단위로 귀속된다. 데이터셋 고정 API는 저장된 최신 annotation revision ID만 받아 label·anchor·cohort·검색 계획·annotation provenance를 서버에서 다시 해석하므로 클라이언트가 학습 정답을 주입할 수 없다.

필수 환경변수는 `INTELLIGENCE_DATABASE_URL`(PostgreSQL libpq 연결 문자열), `KIWOOM_APP_KEY`, `KIWOOM_SECRET_KEY`, `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`이다. KIS 종목 master는 `scripts/load_kis_symbols_to_supabase.py`로 `domestic_symbols`에 먼저 적재돼 있어야 한다(자격증명 불필요, DB 연결 문자열만 필요). 세션 레벨 설정을 쓰므로 transaction-mode 풀러가 아닌 직접 연결 또는 session-mode 풀러를 사용한다. 전체 검증의 Playwright E2E는 로컬 Google Chrome을 headless로 사용한다. 자격증명과 export 파일은 저장소에 커밋하지 않는다.

```bash
# API — 단일 프로세스 + 인프로세스 FIFO writer. 교차 프로세스 직렬화는 Postgres advisory lock(pg_advisory_xact_lock)이 담당한다.
uv run --group server uvicorn finlabs_intelligence.api.runtime:app --host 127.0.0.1 --port 8000

# Web — 별도 터미널
cd finlabs_intelligence/web
bun install --frozen-lockfile
bun run dev

# 전체 오프라인 검증
./scripts/verify-news-intelligence.sh
```

화면과 manifest는 historical backfill을 `historical_publication_proxy` cohort와 `published_at_proxy` anchor로 명시하며 canonical live `t0`로 표현하지 않는다. `POST /api/datasets`는 immutable 스냅샷만 PostgreSQL에 고정하고, `POST /api/datasets/{dataset_id}/exports`가 선택한 DB·JSON·CSV sink를 별도 idempotency 단위로 내보낸다. 각 artifact는 pending 상태를 먼저 기록한 뒤 임시 파일 `fsync`와 원자적 rename을 수행하며, rename 뒤 상태 기록이 끊겨도 checksum으로 복구한다. 검색 완전성·전체 Naver 호출 계획, 종목원 stale 상태, annotation revision·actor·rule evidence, reaction 출처와 제외 사유, sink별 성공/실패도 함께 고정한다. JSON/CSV는 OS 사용자 데이터 디렉터리 아래 `news-intelligence-exports/`에 backend가 정한 안전한 이름으로 기록된다. 전체 검증에는 실제 FastAPI, 일회용 Postgres 스키마와 headless Chrome을 사용하는 catalog→chart→news→annotation revisions→freeze→export E2E가 포함된다.
