# FinLabs 통합 계획서 (v3.0)

## 1. 목적

FinLabs의 뉴스 수집, 실시간 시장 데이터, 장 운영 정보, 저장소와 운영 도구를
브로커 독립적인 계층 구조로 통합한다. 이 문서는 전체 방향, 구현 순서와
모듈 간 계약만 관리한다. 상세 정책은 각 소유 모듈의 PLAN을 단일 원본으로
사용한다.

## 2. 설계 원칙

1. 브로커 SDK는 전송과 파싱만 담당하며 FinLabs 저장소를 알지 않는다.
2. Redis는 전달 계층이고 PostgreSQL과 검증된 Parquet가 영구 원본이다.
3. PostgreSQL 단일 인스턴스에서 `control`, `market`, `news` 스키마를 분리한다.
4. 틱, 호가와 정제 기사 본문은 수년간 연구 가능한 형태로 보존한다.
5. CLI, Discord, 웹과 GUI는 재사용 가능한 orchestration/domain 로직 위에 둔다.
6. Windows, macOS, Linux에서 같은 환경변수와 `uv run` 계약을 사용한다.

## 3. 모듈별 계획

| 영역 | 단일 원본 |
|---|---|
| 뉴스 수집·파싱·분석 | [modules/news/PLAN.md](modules/news/PLAN.md) |
| KIS WebSocket 실시간 수집 | [modules/brokers/kis/PLAN.md](modules/brokers/kis/PLAN.md) |
| Toss 장 운영 정보 | [modules/brokers/toss/PLAN.md](modules/brokers/toss/PLAN.md) |
| PostgreSQL·TimescaleDB·Parquet·백업 | [modules/storage/PLAN.md](modules/storage/PLAN.md) |
| Redis Streams·워커·구독·관측성 | [modules/orchestration/PLAN.md](modules/orchestration/PLAN.md) |

정책을 다른 PLAN에 복사하지 않는다. 교차 모듈 문서는 소유 문서로 링크하고,
계약 변경 시 이 문서의 의존관계와 구현 상태만 갱신한다.

## 4. 전체 아키텍처

```text
KIS WebSocket
  -> Redis Streams
     -> TimescaleDB writer
     -> 1-minute candle aggregator
     -> Parquet archive writer
     -> Redis Pub/Sub live broadcast

RSS / Article Fetcher
  -> PostgreSQL news schema

Toss Market Calendar
  -> Toss SDK -> Toss Adapter -> PostgreSQL market schema

Monitoring Core
  -> Rich CLI
  -> Discord
  -> Future FastAPI/WebSocket and PyQt
```

## 5. 전환 정책

- 신규 쓰기 경로는 PostgreSQL/TimescaleDB, Redis Streams, Parquet을 사용한다.
- 기존 `warehouse.duckdb`, `news.db`, SQLite는 이동하거나 마이그레이션하지 않고
  읽기 전용 레거시 보관소로 유지한다.
- 신규 인프라는 빈 상태로 시작하며 이중 쓰기를 하지 않는다.
- MongoDB는 도입하지 않는다.
- 원문 HTML은 영구 보관하지 않고 정제 기사 본문만 저장한다.

## 6. 구현 순서

### 단계 1: 기반 인프라

- TimescaleDB와 Redis AOF Docker Compose 구성
- 공통 환경설정, 비밀정보 마스킹과 크로스플랫폼 경로
- Alembic 단일 revision 체인과 세 PostgreSQL 스키마

완료 기준:

- Windows, macOS, Linux에서 Compose와 `uv run` 연결 검사가 성공한다.
- 빈 DB 마이그레이션 후 모든 스키마가 같은 revision을 보고한다.

### 단계 2: 이벤트 전송과 구독 제어

- Redis Streams, Consumer Group, DLQ와 멱등성
- KIS WebSocket 수집기와 동적 구독 CLI
- 구독 자동 복원과 명시적 초기화

완료 기준:

- 강제 종료된 메시지가 회수되고 중복 행 없이 처리된다.
- 재시작 시 활성 구독이 복원되고 초기화 시 실제 구독도 해제된다.

### 단계 3: 시장 데이터 영구화

- TimescaleDB 틱·호가, canonical 1분봉과 임의 N분 조회
- 시간별 Parquet, 일별 병합, 검증과 hot retention
- Toss 장 운영 정보와 세션 분류

완료 기준:

- 세션 경계를 넘는 캔들이 생성되지 않는다.
- `daily_verified` 전에는 hot data가 삭제되지 않는다.

### 단계 4: 뉴스 저장 개편

> **상태: 이전 완료** — `rss_items`·`articles`·`article_analyses`·`article_entities`·`article_entity_extractions`·`pipeline_runs`·`domestic_symbols`·`overseas_symbols`가 finlabs_intelligence와 공유하는 Supabase PostgreSQL로 이전됨(`INTELLIGENCE_DATABASE_URL`, psycopg). DuckDB와 파일 잠금은 제거. repository Protocol 추상화와 별도 `news` 스키마 분리는 후속 과제.

- RSS 상태·중복 관리를 PostgreSQL로 이전 ✅
- 언론사별 parser registry와 정제 본문 저장 ✅
- 재시도, 영구 실패와 parser version 기반 재처리 ✅

완료 기준:

- 동일 기사 재수집이 중복 레코드를 만들지 않는다.
- 원문 HTML이 영구 저장소에 남지 않는다.

### 단계 5: 관측성과 알림

- 공통 상태 DTO와 비동기 상태 스트림
- Rich 실시간 모니터, JSON 출력, 감사 로그와 Discord

완료 기준:

- 전체 파이프라인 상태가 기본 1초 주기로 갱신된다.
- 알림 억제, 심각도 상승과 정상 복구 정책이 검증된다.

### 단계 6: 백업과 복구

- PostgreSQL 백업, Parquet 복제, 암호화와 보조 대상 검증
- 주간 체크섬 검증과 월간 격리 복구 훈련

완료 기준:

- 암호화 백업을 임시 DB로 복원해 핵심 조회가 성공한다.
- RPO/RTO 위반이 실시간 모니터링과 Discord에 표시된다.

## 7. 현재 진행 상태

| 항목 | 상태 |
|---|---|
| 뉴스 RSS 수집과 SQLite 기반 초기 파이프라인 | 구현됨, PostgreSQL 전환 예정 |
| 국내·해외 종목 마스터 갱신 CLI | 구현됨 |
| Toss 장 운영 정보 SDK와 calendar adapter | 구현됨 |
| PostgreSQL/TimescaleDB·Redis·Parquet 신규 플랫폼 | 계획 확정, 구현 전 |
| KIS 실시간 구독 파이프라인 | 계획 확정, 구현 전 |
| 실시간 모니터링·Discord·백업 자동화 | 계획 확정, 구현 전 |

## 8. 공통 검증

- 실제 KIS/Toss API는 단위 테스트에서 호출하지 않는다.
- Redis 장애, PostgreSQL 실패, 중복·지연 메시지, 디스크 부족,
  보조 백업 대상 분리와 Discord 실패를 통합 테스트에서 모사한다.
- 구조 경계는 AST 기반 architecture test로 검증한다.
- 각 단계에서 targeted test, 전체 pytest, Ruff, compileall과
  Compose healthcheck를 수행한다.
