# kis_cli 패키지 개요

`kis_cli`는 FinLabs의 Korea Investment & Securities Open API 기반 시장 데이터 수집 CLI 애플리케이션입니다. 로컬 개발에서는 `python -m kis_cli`로 실행하며, 현재 구현 범위는 설정 관리, 인증 확인, 심볼 마스터 다운로드/검색, OHLCV 이력 수집/저장, 저장 데이터 조회/내보내기, 로컬 저장소 점검입니다.

KIS API 트랜스포트·파싱은 `modules.brokers.kis` SDK가 담당하고, `kis_cli`는 그 SDK를 소비하는 애플리케이션 계층입니다. `kis_cli`는 점진적으로 `modules.orchestration` 위의 **thin transport / legacy app shell**로 이전하는 중이며, 아래 `services`·`core`·`storage`는 마이그레이션이 끝날 때까지 남아 있는 transitional 계층입니다. 사용자 CLI 실행 방식(`python -m kis_cli`)은 이 이전 과정에서도 그대로 유지됩니다.

## 패키지 구성

- `cli/`: Typer 기반 CLI 명령 정의와 콘솔 출력/파일 export 처리
- `config/`: _(transitional)_ 설정 파일 생성, 프로필 추가/수정/삭제, 환경변수/프로필 해석 — `modules/config`로 이전 예정
- `core/`: _(transitional)_ 레거시 동기 REST 클라이언트와 파일 기반 토큰 캐시 — 삭제 또는 `modules.brokers.kis` auth로 통합 예정
- `services/`: _(transitional)_ CLI와 storage/SDK를 잇는 유즈케이스 계층 — 새 유즈케이스는 `modules.orchestration`에 작성
- `storage/`: _(transitional)_ 앱 SQLite DB, DuckDB warehouse 쓰기, 중복 방지 insert/upsert, 저장소 점검 — warehouse **읽기**는 `modules.storage`/`modules.orchestration.query`로 이동 완료

## 주요 CLI 기능

```bash
python -m kis_cli config init
python -m kis_cli config add
python -m kis_cli config validate
python -m kis_cli config update
python -m kis_cli config delete

python -m kis_cli auth test
python -m kis_cli db init
python -m kis_cli db schema
python -m kis_cli db counts
python -m kis_cli logs runs
python -m kis_cli logs api

python -m kis_cli symbols download --market NASDAQ
python -m kis_cli symbols download --all
python -m kis_cli symbols search --query apple

python -m kis_cli chart daily --profile real --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
python -m kis_cli chart history --profile real --symbol 005930 --period W --start 2025-01-01 --end 2026-05-07 --save

python -m kis_cli query ohlcv --symbol AAPL
python -m kis_cli query ohlcv --symbol AAPL --format json
python -m kis_cli query ohlcv --symbol AAPL --export ./exports/aapl.csv
```

## 저장 위치

기본 경로는 `platformdirs`를 통해 OS별 사용자 디렉터리에 저장합니다.

- 설정: `~/.config/kis-cli/config.yaml`
- 프로필 시크릿: 설정 파일과 같은 폴더의 `profiles.env`
- 토큰 캐시: `~/.cache/kis-cli/tokens/`
- App DB: `~/.local/share/kis-cli/app.db`
- DuckDB warehouse: `~/.local/share/kis-cli/warehouse.duckdb`

API 키, 시크릿, 계좌번호, 토큰은 패키지 소스 내부에 저장하지 않습니다.
