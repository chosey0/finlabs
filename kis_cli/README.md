# kis_cli 패키지 개요

`kis_cli`는 FinLabs의 Korea Investment & Securities Open API 기반 시장 데이터 수집 CLI 애플리케이션입니다. 로컬 개발에서는 `python -m kis_cli`로 실행하며, 현재 구현 범위는 설정 관리, 인증 확인, 심볼 마스터 다운로드/검색, OHLCV 이력 수집/저장, 저장 데이터 조회/내보내기, 로컬 저장소 점검입니다.

## 패키지 구성

- `cli/`: Typer 기반 CLI 명령 정의와 콘솔 출력/파일 export 처리
- `config/`: 설정 파일 생성, 프로필 추가/수정/삭제, 환경변수/프로필 해석
- `core/`: KIS REST 인증, REST 클라이언트, 현재가/OHLCV/심볼 마스터 파서
- `services/`: CLI와 core/storage를 잇는 유즈케이스 계층
- `storage/`: 앱 SQLite DB, DuckDB warehouse, 중복 방지 insert/upsert, 조회, 저장소 점검

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

python -m kis_cli symbols download --market KOSPI
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
