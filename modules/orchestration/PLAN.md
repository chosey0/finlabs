# Orchestration 계획

## 범위

Redis Streams, 구독 목표 상태, 워커 실행, 캔들 집계, 실시간 모니터링,
Discord 알림과 크로스플랫폼 실행을 소유한다. 브로커 SDK와 저장 구현은
각 모듈 PLAN의 계약을 사용한다.

## Redis 전달

- Consumer Group 기반 at-least-once 전달
- 저장 트랜잭션 또는 Parquet 체크포인트 성공 후에만 `XACK`
- 60초 이상 pending 메시지는 `XAUTOCLAIM`으로 회수
- 5회 실패 시 스트림별 DLQ로 이동
- DLQ에 원본 payload, 오류, 횟수, 최초·최종 실패 시각 저장
- CLI에서 DLQ 조회·재처리·폐기 지원
- DB 적재기와 아카이브 워커는 별도 Consumer Group 사용
- Redis Pub/Sub은 비영속 실시간 화면 전파에만 사용
- AOF `everysec` 사용

## Stream 보존

- 시간 상한 기본값 24시간
- 스트림별 최대 메시지 수
- 실행 환경 메모리 기반 상한
- Redis 컨테이너 메모리 기본값: 시스템 메모리의 20%
- `maxmemory`: 컨테이너 한도의 75%
- Stream 예산: `maxmemory`의 60%
- 어느 기준이든 초과하면 모든 그룹이 ACK한 안전 구간부터 정리
- 메모리 임계 상황을 시간·건수보다 우선
- 정리 감사 로그 저장 실패 시 정리를 실행하지 않음

## 구독과 세션

- CLI로 틱·호가 구독을 동적으로 추가·해제한다.
- PostgreSQL에 목표 상태를 저장하고 시작 시 자동 복원한다.
- 초기화는 이력을 보존하고 목표 상태 비활성화와 실제 구독 해제를 수행한다.
- 세션은 `regular`, `pre_market`, `after_market`, `nxt`, `unknown`으로 분리한다.
- 세션 경계를 넘어 데이터를 집계하지 않는다.

## 캔들

- 1분봉을 canonical 영구 데이터로 생성한다.
- N분봉은 1~1440 정수 범위에서 1분봉으로 동적 집계한다.
- 버킷은 세션 시작 시각에 정렬한다.
- 분 종료 10초 후 최초 확정하고 지연 틱은 `corrected`로 반영한다.
- 장 종료 후 Parquet 원시 데이터와 일별 재조정한다.

## 과거 시장 이벤트 라벨

- KIS/Toss adapter가 정규화한 일봉으로 브로커 독립적인 급등 이벤트를 추출한다.
- 기본 조건은 거래대금 100억 원 이상이며 1일 또는 최근 3거래일 수익률이
  10% 이상인 세션이다.
- 결과는 `market.surge_events` 소유 데이터로 저장하고 뉴스 모듈은
  과거 기사 검색과 사례 라이브러리 구축을 위해 읽기만 한다.

## 독립 프로세스

- KIS WebSocket 수집기
- PostgreSQL 적재 워커
- 1분봉 집계 워커
- Parquet 아카이브 워커
- 뉴스 수집기
- 모니터링/알림 프로세스
- 백업/복구 검증 워커

개발에서는 인프라를 Docker Compose로, Python 서비스를 `uv run`으로 실행한다.
무인 운영은 Compose `workers` profile과 `restart: unless-stopped`를 사용한다.
`launchd`, `systemd`, Windows Service/Task Scheduler는 선택적 외부 연동이며
애플리케이션이 직접 제어하지 않는다.

모든 워커는 종료 신호, heartbeat, 재연결, 지수 백오프와 체크포인트 복원을
지원한다. 경로는 `pathlib`/`platformdirs`를 사용한다.

## 로그와 감사

- JSON 로그를 콘솔과 `db/logs/<service>/` 회전 파일에 동시 기록
- 중요 이벤트는 `control.audit_logs`에 영구 저장
- 공통 필드: `trace_id`, `event_id`, `run_id`, `service`, `instance_id`,
  `level`, `timestamp`
- 토큰, 계좌번호, Webhook URL과 DSN 자동 마스킹

보존 기본값:

- DEBUG 14일
- INFO 90일
- ERROR 1년
- 감사 로그 영구

## 실시간 모니터링

- Rich 대시보드를 기본 1초 주기로 갱신한다.
- `--json` 실시간 출력도 지원한다.
- 워커 상태, KIS 연결·구독 수, Stream 유입량·메모리, lag/pending, DLQ,
  PostgreSQL 지연, 캔들, 아카이브와 뉴스 수집 상태를 표시한다.
- 모니터 종료는 워커에 영향을 주지 않는다.

재사용 가능한 핵심 DTO와 인터페이스:

- `SystemSnapshot`
- `ServiceHealth`
- `AlertEvent`
- 현재 상태 조회
- 비동기 상태 스트림 구독
- 경고 확인·해제

핵심 로직은 Rich, Discord, FastAPI와 PyQt를 import하지 않는다. CLI, Discord,
향후 웹/PyQt UI는 Redis와 PostgreSQL을 직접 해석하지 않는다.

## Discord 알림

- 상태 전환 시 즉시 발송
- 동일 경고 묶음 처리와 기본 5분 재알림 제한
- 심각도 상승 시 제한과 무관하게 즉시 발송
- 정상 복구 알림 별도 발송
- 발송 실패도 구조화 로그와 감사 이력에 기록

## 완료 기준

- 워커 강제 종료 후 pending 메시지가 회수된다.
- 중복 전달에도 저장 결과가 하나로 유지된다.
- Stream 정리 전 감사 로그가 반드시 기록된다.
- 1초 주기로 시스템 상태가 갱신된다.
- 동일 경고 억제, 심각도 상승과 복구 알림이 검증된다.
- fake adapter를 통해 웹/PyQt 소비자가 핵심 상태 로직을 재사용할 수 있다.
