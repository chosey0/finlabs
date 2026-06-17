# Storage 계획

## 범위

PostgreSQL/TimescaleDB 스키마, 영구 데이터 쓰기, Parquet 아카이브,
보존 정책, 마이그레이션과 백업·복구를 소유한다. Redis 전달과 워커 제어는
[orchestration PLAN](../orchestration/PLAN.md)이 소유한다.

## PostgreSQL

단일 인스턴스에서 스키마를 분리한다.

| 스키마 | 책임 |
|---|---|
| `control` | 구독 목표, 명령·실행 이력, 정책, 감사 로그, 알림, 백업 이력 |
| `market` | 종목 마스터, 틱, 호가, 캔들, 장 운영 정보, 급등 이벤트, 아카이브 매니페스트 |
| `news` | RSS 메타데이터, 중복 상태, 정제 본문, 파싱 결과, 엔티티, 이벤트 |

- TimescaleDB는 최근 틱·호가의 hot store로 사용한다.
- hot retention 기본값은 3일이며 CLI/DB 정책으로 변경 가능하다.
- 결정적 `event_id`와 고유 제약으로 재처리 중복을 방지한다.
- `daily_verified` 아카이브가 없으면 hot data를 삭제하지 않는다.

## Alembic

- 세 스키마를 단일 revision 체인으로 관리한다.
- 서비스 시작 시 revision 일치 여부만 검사한다.
- 자동 적용하지 않고 명시적 CLI 명령으로만 실행한다.
- 적용 전 백업과 사전 검증을 강제한다.
- 결과와 실패를 감사 로그에 기록한다.

## Parquet

- 틱과 10단계 호가를 장중 시간별 파일로 기록한다.
- 파티션은 `broker/market/date/hour`이며 종목 디렉터리는 만들지 않는다.
- 장 종료 후 일별 파일로 병합한다.
- 행 수, 시간 범위와 체크섬 검증 후 `daily_verified`로 전환한다.
- 검증 성공 후 시간별 파일을 삭제할 수 있다.

## 백업과 복구

- PostgreSQL 논리 백업: 매일
- Parquet 체크섬 매니페스트와 보조 대상 복제: 시간별
- 로컬 기본 경로: `db/backups/`
- 보조 대상: 외장 디스크, NAS, Google Drive, Apple iCloud 동기화 경로
- 복사 후 크기와 체크섬을 검증한다.
- 미연결, 동기화 지연과 용량 부족은 경고하되 수집을 중단하지 않는다.
- 보조 사본은 복사 전 애플리케이션에서 암호화한다.
- 암호화 전·후 체크섬을 모두 기록한다.
- 키는 OS Keyring 우선, 오프라인 키 파일 대체를 지원한다.
- 키는 `.env`, PostgreSQL, 로그와 Discord에 기록하지 않는다.

복구 목표:

- PostgreSQL RPO 24시간, RTO 4시간
- Parquet 원시 데이터 RPO 1시간 이내
- 매주 체크섬 표본 검증
- 매월 격리된 임시 PostgreSQL에 전체 복원과 핵심 조회 검증

## 로컬 디렉터리

```text
db/
  compose.yaml
  migrations/
  data/{postgres,redis,objects}/
  backups/
  logs/
  scripts/
```

`db/data/`, `db/backups/`, `db/logs/`와 비밀 파일은 Git에서 제외한다.

## 완료 기준

- 빈 DB와 기존 revision 모두에서 Alembic 적용·검사가 성공한다.
- 중복 이벤트 삽입이 고유 제약으로 차단된다.
- `daily_verified` 이전에는 retention 삭제가 실행되지 않는다.
- 암호화 백업을 임시 DB로 복원하고 핵심 조회가 성공한다.
