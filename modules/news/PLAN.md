# Airflow 도입 시점

## 결론

현재는 Airflow 도입이 이릅니다. 우선 Linux 서버에서 `systemd timer`로 단일 CLI 파이프라인을 운영합니다.

Airflow 도입 시점은 RSS 수집 → 본문 수집 → 분석의 세 단계가 모두 구현되고, 단계별 재시도/백필/모니터링 필요성이 실제 운영 문제로 나타날 때.

## 단계별 전략

1. 현재 단계
    - 저장소 루트에서 `uv run python -m modules.news.main collect-rss`
    - `uv run python -m modules.news.main collect-articles --limit 100`
    - `uv run python -m modules.news.main analyze --limit 100`
    - `NEWS_DB_PATH` 또는 `--db-path`로 운영 DB 경로 지정
    - 모든 작업은 기본키와 본문 해시를 기준으로 멱등하게 실행
    - `pipeline_runs`에 성공·실패 상태, 처리 건수, 오류 메시지 저장
    - `systemd/finlabs-news.service`와 `systemd/finlabs-news.timer`로 주기 실행
    - DB별 잠금 파일로 DuckDB writer를 하나의 CLI 프로세스로 직렬화

2. Airflow 검토 단계
   다음 조건 중 3개 이상이 충족되면 파일럿을 시작.
    - 세 단계가 서로 다른 주기나 재시도 정책을 요구함
    - 언론사와 크롤러 수가 지속적으로 증가함
    - 특정 날짜나 언론사만 다시 처리하는 백필이 자주 필요함
    - 실패 탐지와 수동 재실행에 주당 30분 이상 사용함
    - 한 번의 실행이 다음 스케줄까지 끝나지 않음
    - 운영자가 웹 UI에서 실행 상태와 로그를 확인해야 함
    - 여러 서버나 컨테이너에서 작업을 실행해야 함

3. Airflow 도입 단계
    - DAG는 RSS 수집 → 본문 수집 → 분석 → 완료 검증으로 구성
    - 기사 한 건마다 Airflow Task를 만들지 않고, 언론사나 배치 단위로 Scrapy 작업을 실행
    - XCom에는 ID, 건수, 저장 위치 같은 작은 메타데이터만 전달
    - Airflow 메타데이터는 PostgreSQL에 저장
    - DuckDB를 유지한다면 단일 writer Task로 쓰기를 직렬화
    - 병렬 작업자가 직접 DB를 써야 한다면 RSS 운영 저장소를 PostgreSQL로 이전

## 핵심 제약
Airflow는 스케줄러 외에도 웹서버, DAG 프로세서, 메타데이터 DB가 필요한 운영 시스템입니다.

현재 규모에서는 유지비가 자동화 이익보다 큽니다.

또한 DuckDB 파일은 기본적으로 하나의 writer 프로세스를 전제로 합니다.

Airflow 작업을 병렬 프로세스나 여러 서버에서 실행하면 현재 저장 구조와 충돌할 수 있으므로, Airflow 도입과 DuckDB 병렬 쓰기를 동시에 시작하지 않습니다.

## 권장 기본값
  - 단일 서버: systemd timer + CLI + DuckDB
  - 수집 및 분석 파이프라인이 안정된 후: Airflow LocalExecutor 파일럿
  - 다중 서버 또는 병렬 writer 필요 시: PostgreSQL 전환 후 Airflow 운영
