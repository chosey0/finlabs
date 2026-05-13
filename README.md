# kis-cli

`kis-cli`는 Korea Investment & Securities Open API를 사용해 국내/해외 주식 시장 데이터를 수집하고 저장하는 Python CLI 프로젝트입니다. CLI 명령은 `kiscli`로 제공됩니다.

현재 구현 범위는 설정 관리, REST 인증 확인, 심볼 마스터 다운로드/검색, OHLCV 이력 수집/저장, 저장 데이터 조회/내보내기, 로컬 저장소 점검입니다.

이 프로젝트는 시장 데이터 수집용 CLI입니다. UI, 웹 대시보드, 차트 렌더링, 자동매매, 주문 실행, 전략/백테스트 기능은 포함하지 않습니다.

## 주요 기능

- 프로필 기반 설정 관리와 시크릿 분리 저장
- KIS REST access token 발급/캐시/검증
- KOSPI, KOSDAQ, 해외 시장 심볼 마스터 다운로드와 warehouse upsert
- 저장된 심볼 검색, query 유사도 기반 정렬, realtime symbol 출력
- 국내/해외 OHLCV 이력 수집
- `--save` 사용 시 `ohlcv_bars`에 시가/고가/저가/종가/거래량/대비/등락률/거래대금을 중복 방지 저장
- 저장된 일봉 OHLCV 조회, table/json/csv 출력, csv/json export
- 심볼/OHLCV 저장 작업 로그를 앱 SQLite DB에 기록
- 앱용 SQLite DB와 시장 데이터용 DuckDB warehouse 초기화/점검
- Supabase/PostgreSQL canonical store용 `symbols`, `ohlcv_bars` 스키마 제공

## 설치

개발 환경에서는 `uv` 사용을 권장합니다.

```bash
uv sync
```

Supabase/PostgreSQL 스키마 초기화까지 사용할 경우:

```bash
uv sync --extra postgres
```

CLI 실행:

```bash
uv run kiscli --help
```

`uv`를 사용하지 않는 경우:

```bash
python -m pip install -e .
kiscli --help
```

Supabase/PostgreSQL 지원을 포함해 설치하려면:

```bash
python -m pip install -e ".[postgres]"
```

## 빠른 시작

1. 설정 파일과 프로필을 준비합니다.

```bash
uv run kiscli config init
uv run kiscli config add
```

1. 설정을 검증합니다.

```bash
uv run kiscli config validate --profile csq1404
```

1. REST 인증을 확인합니다.

```bash
uv run kiscli auth status --profile csq1404
uv run kiscli auth test --profile csq1404
```

1. DB를 초기화합니다.

```bash
uv run kiscli db init
```

Supabase/PostgreSQL canonical store를 초기화하려면 Supabase Dashboard의 Connection Method 중 **Transaction pooler** connection string을 DSN으로 사용합니다. 해당 값을 환경변수로 주입한 뒤 `--store supabase`를 실행합니다.

```bash
export KISCLI_SUPABASE_DB_DSN='postgresql://USER:PASSWORD@HOST:6543/postgres'
uv run kiscli db init --store supabase
```

환경변수가 없으면 CLI가 DSN을 비공개 입력으로 요청하고, 입력값은 사용자 config 디렉터리의 `profiles.env`에 저장해 이후 Supabase 명령에서 재사용합니다.
URL 형태의 DSN에서 password에 `!@#$` 같은 특수문자가 포함되어 있으면 CLI가 연결 직전에 username/password 부분을 URL encoding합니다.

1. 심볼 마스터를 다운로드합니다.

```bash
uv run kiscli symbols download --market KOSPI
uv run kiscli symbols download --market NASDAQ
uv run kiscli symbols download --market NASDAQ --store supabase
```

1. OHLCV를 수집하고 저장합니다.

```bash
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save --store supabase
```

1. 저장된 일봉 데이터를 조회합니다.

```bash
uv run kiscli query ohlcv --symbol 005930
```

1. 작업 이력이나 API 오류를 확인합니다.

```bash
uv run kiscli logs runs --limit 20
uv run kiscli logs api --limit 20
```

## 설정과 로컬 파일

기본 경로는 OS별 사용자 디렉터리를 사용합니다.

```text
Config: ~/.config/kis-cli/config.yaml
Secrets: ~/.config/kis-cli/profiles.env
Cache:  ~/.cache/kis-cli/
Data:   ~/.local/share/kis-cli/
App DB: ~/.local/share/kis-cli/app.db
Warehouse: ~/.local/share/kis-cli/warehouse.duckdb
```

## 저장소 역할

현재 로컬 실행 상태와 작업 로그는 SQLite app DB에 저장합니다. 시장 데이터는 DuckDB warehouse에 저장하며, Supabase/PostgreSQL은 원천 시장 데이터를 여러 환경에서 공유하기 위한 canonical store로 확장 중입니다.

권장 역할 분리는 다음과 같습니다.

```text
SQLite app DB          # kiscli 내부 실행 상태와 로컬 작업/API 로그
Supabase/PostgreSQL    # symbols, ohlcv_bars 원천 시장 데이터
DuckDB                 # 로컬 분석 mart, feature engineering, 학습용 snapshot/export
```

API 키, API 시크릿, 계좌번호, 토큰은 패키지 소스 안에 저장하지 않습니다. CLI 출력에서도 민감 값은 마스킹합니다.
`symbols download`와 `chart ... --save` 실행 기록은 앱 DB의 `ingest_runs`, `api_logs` 테이블에 저장됩니다. 저장되는 시각 값은 KST ISO 형식입니다.

## 설정 명령

설정 파일 생성:

```bash
uv run kiscli config init
uv run kiscli config init --profile mock --environment mock
uv run kiscli config init --path ./config.yaml --force
```

프로필 관리:

```bash
uv run kiscli config add
uv run kiscli config validate
uv run kiscli config validate --profile csq1404
uv run kiscli config update --profile csq1404
uv run kiscli config delete --profile csq1404 --yes
```

`config add`와 `config update`는 대화형 프롬프트로 프로필명, 환경, 계좌번호, APP key, Secret key, 소유자, 만료일을 입력받습니다.

## 인증

KIS REST access token을 발급하거나 유효한 캐시 토큰을 재사용합니다.

```bash
uv run kiscli auth test --profile csq1404
uv run kiscli auth test --profile csq1404 --refresh
uv run kiscli auth status --profile csq1404
uv run kiscli auth status --all
uv run kiscli auth clear --profile csq1404
```

`--refresh`를 사용하면 유효한 캐시가 있어도 새 토큰을 요청합니다.

`auth status`는 KIS 서버에 요청하지 않고 로컬 토큰 캐시만 확인합니다. `--profile`을 생략하면 `active_profile`을 사용하고, `--all`은 모든 프로필의 토큰 상태를 보여줍니다. 상태값은 다음과 같습니다.

- `valid`: 캐시 토큰이 있고 만료 5분 전 기준으로 유효
- `expiring`: 캐시 토큰이 아직 만료되지 않았지만 5분 이내 만료
- `expired`: 캐시 토큰 만료
- `none`: 토큰 캐시 파일 없음
- `invalid`: 캐시 파일이 손상됐거나 프로필/환경과 맞지 않음

토큰 만료 시각은 CLI 출력에서 KST 기준으로 표시되며, `auth status`는 남은 시간도 함께 보여줍니다. `auth clear`는 캐시된 토큰을 삭제하며 KIS 서버에는 요청하지 않습니다.

## DB 관리

로컬 저장소 초기화:

```bash
uv run kiscli db init
uv run kiscli db init --path ./warehouse.duckdb
```

Supabase/PostgreSQL canonical store 초기화:

```bash
export KISCLI_SUPABASE_DB_DSN='postgresql://USER:PASSWORD@HOST:6543/postgres'
uv run kiscli db init --store supabase
```

`--store supabase`는 `symbols`, `ohlcv_bars` 테이블과 조회용 인덱스를 생성합니다. 연결 문자열은 Supabase Dashboard의 Connection Method 중 **Transaction pooler** connection string을 사용하고, `KISCLI_SUPABASE_DB_DSN` 환경변수 또는 `profiles.env`에서 읽습니다.
환경변수가 없고 `profiles.env`에도 값이 없으면 CLI가 DSN을 비공개 입력으로 요청한 뒤 저장합니다.

DB 구조 확인:

```bash
uv run kiscli db schema
uv run kiscli db schema --path ./warehouse.duckdb
```

테이블별 레코드 수 확인:

```bash
uv run kiscli db counts
uv run kiscli db counts --path ./warehouse.duckdb
```

현재 주요 테이블은 다음과 같습니다.

- `symbols`
- `ohlcv_bars`
- `realtime_ticks`

중복 방지는 DB 제약조건으로 처리합니다.

```sql
UNIQUE (market, symbol)
UNIQUE (market, symbol, interval, timestamp)
UNIQUE (market, symbol, exchange_ts, seq)
```

## 로그 조회

`logs` 명령은 기존 app SQLite DB를 읽기만 합니다. DB가 아직 없으면 먼저 `db init`을 실행합니다.

최근 저장 작업 이력:

```bash
uv run kiscli logs runs
uv run kiscli logs runs --limit 50
uv run kiscli logs runs --status failed
uv run kiscli logs runs --kind symbols --market KOSPI
uv run kiscli logs runs --symbol AAPL --since 2026-05-08
```

최근 API/다운로드 기록:

```bash
uv run kiscli logs api
uv run kiscli logs api --limit 50
uv run kiscli logs api --endpoint ohlcv
```

스크립트에서 사용하려면 `--format json` 또는 `--format csv`를 지정합니다.
커스텀 app DB 경로를 확인하려면 `--path ./app.db`를 지정합니다.

## 심볼 마스터

심볼 마스터 다운로드:

```bash
uv run kiscli symbols download --market KOSPI
uv run kiscli symbols download --market KOSDAQ
uv run kiscli symbols download --market NASDAQ
uv run kiscli symbols download --market NASDAQ --store supabase
uv run kiscli symbols download --all
```

`--store duckdb`가 기본값입니다. `--store supabase`를 사용하면 `KISCLI_SUPABASE_DB_DSN`으로 연결한 Supabase/PostgreSQL의 `symbols` 테이블에 upsert합니다. `--db-path`는 DuckDB 전용 옵션입니다.
환경변수가 없고 `profiles.env`에도 값이 없으면 DSN을 비공개 입력으로 요청한 뒤 저장합니다.

커스텀 DB 경로:

```bash
uv run kiscli symbols download --market NASDAQ --db-path ./warehouse.duckdb
```

저장된 심볼 검색:

```bash
uv run kiscli symbols search --query apple
uv run kiscli symbols search --query 삼성 --limit 10
uv run kiscli symbols search --query apple --market NASDAQ
```

검색 결과는 query와 더 유사한 순서로 정렬됩니다. 출력에는 `Market`, `Symbol`, `Realtime symbol`, `Korean name`, `English name`, `Currency`, `Type`이 포함됩니다.

지원 심볼 마스터 시장:

```text
KOSPI, KOSDAQ, NASDAQ, NYSE, AMEX,
SHANGHAI, SHANGHAI_INDEX, SHENZHEN, SHENZHEN_INDEX,
TOKYO, HONGKONG, HANOI, HOCHIMINH
```

## OHLCV 수집

일봉 수집:

```bash
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07
```

저장까지 수행:

```bash
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
uv run kiscli chart daily --profile csq1404 --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save
uv run kiscli chart daily --profile csq1404 --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save --store supabase
```

`--save --store supabase`는 Supabase/PostgreSQL의 `ohlcv_bars` 테이블에 중복 방지 insert를 수행합니다. 현재 `chart` 명령의 market 해석은 로컬 DuckDB `symbols` 테이블을 사용하므로, 먼저 대상 심볼을 로컬에도 다운로드해두어야 합니다.
환경변수가 없고 `profiles.env`에도 값이 없으면 DSN을 비공개 입력으로 요청한 뒤 저장합니다.

기간 단위 명령:

```bash
uv run kiscli chart weekly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07 --save
uv run kiscli chart monthly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07 --save
uv run kiscli chart yearly --profile csq1404 --symbol 005930 --start 2020-01-01 --end 2026-05-07 --save
```

고급/범용 history 명령:

`daily`, `weekly`, `monthly`, `yearly` 대신 `--period`를 직접 지정하고 싶을 때 사용합니다. 일반적인 사용 흐름에서는 위 기간 단위 명령을 권장합니다.

```bash
uv run kiscli chart history --profile csq1404 --symbol 005930 --period D --start 2026-04-01 --end 2026-05-07 --save
uv run kiscli chart history --profile csq1404 --symbol 005930 --period W --start 2025-01-01 --end 2026-05-07 --save
```

period 매핑:

```text
D -> 1d
W -> 1w
M -> 1mo
Y -> 1y
```

`chart` 명령은 `symbols` 테이블에서 `--symbol`의 market을 해석합니다. 먼저 `kiscli symbols download`로 대상 시장의 심볼을 저장해두세요. `--end`를 생략하면 오늘 날짜까지 조회합니다.

국내 OHLCV는 응답 제한에 맞춰 가장 오래된 수집일 기준으로 다음 구간을 이어 조회합니다. 해외 개별주식의 일/주/월 OHLCV는 `[해외주식] 해외주식 기간별시세` API(`/dailyprice`)를 사용합니다. 1회 최대 100건을 기준으로, 응답에 다음 `KEYB`가 있으면 같은 `BYMD`에서 다음 묶음을 이어 조회하고, `KEYB`가 없더라도 100건이 꽉 찬 응답이면 가장 오래된 응답일 이전으로 `BYMD`를 이동해 이어 조회합니다. 해외 개별주식 연봉(`Y`)은 지원하지 않습니다.

저장 항목은 시가, 고가, 저가, 종가, 거래량에 더해 KIS 응답에 포함된 대비, 등락률, 거래대금을 함께 저장합니다. 일부 API 응답에 값이 없으면 해당 컬럼은 비워둡니다.

OHLCV 수집 중 KIS가 토큰 만료/인증 오류를 반환하면 토큰을 새로 발급하고 1회만 재시도합니다.

## 저장 데이터 조회와 내보내기

현재 저장 데이터 조회는 일봉(`interval=1d`) 전용입니다. `--market`과 `--interval`은 받지 않고 `--symbol`만 사용합니다.

기본 조회:

```bash
uv run kiscli query ohlcv --symbol AAPL
uv run kiscli query ohlcv --symbol 005930 --limit 30
uv run kiscli query ohlcv --symbol AAPL --all
```

기본 조회는 최신 20개 일봉을 반환합니다. `--all`을 사용하면 날짜 조건에 맞는 모든 일봉을 조회합니다. 조회 결과는 최신 날짜가 먼저 나옵니다.

기간 조회:

```bash
uv run kiscli query ohlcv --symbol AAPL --start 2026-04-01 --end 2026-05-07
uv run kiscli query ohlcv --symbol 005930 --start 20260401 --end 20260507
```

출력 형식:

```bash
uv run kiscli query ohlcv --symbol AAPL --format table
uv run kiscli query ohlcv --symbol AAPL --format json
uv run kiscli query ohlcv --symbol AAPL --format csv
```

파일 내보내기:

```bash
uv run kiscli query ohlcv --symbol AAPL --export ./exports/aapl.csv
uv run kiscli query ohlcv --symbol AAPL --export ./exports/aapl.json
```

CSV/JSON 컬럼:

```text
market,symbol,interval,timestamp,open,high,low,close,volume,change,change_rate,amount
```

`change`, `change_rate`, `amount`는 KIS 응답에 값이 없는 경우 비어 있을 수 있습니다. table 출력도 같은 값들을 `Change`, `Change Rate`, `Amount` 컬럼으로 표시합니다.

## 패키지 구조

```text
kis_cli/
├── cli/       # Typer 루트 앱, 명령별 모듈, Rich 출력, JSON/CSV export
├── config/    # 설정 파일, 프로필, 시크릿 참조 해석
├── core/      # KIS REST 인증/클라이언트/현재가/OHLCV/심볼 파서
├── services/  # CLI 유즈케이스 조립
└── storage/   # 앱 SQLite DB, DuckDB warehouse, repository, 저장소 점검
```

`kis_cli/cli/app.py`는 루트 Typer 앱 조립만 담당합니다. 새 CLI 명령은 `kis_cli/cli/<command>.py`에 명령 그룹별로 추가하고, 실제 작업은 `services/`, `core/`, `storage/`, `config/`로 위임합니다.

각 패키지 폴더에는 더 자세한 설명이 있습니다.

- `kis_cli/README.md`
- `kis_cli/cli/README.md`
- `kis_cli/config/README.md`
- `kis_cli/core/README.md`
- `kis_cli/services/README.md`
- `kis_cli/storage/README.md`

## 개발

의존성 동기화:

```bash
uv sync
```

테스트:

```bash
uv run pytest
```

특정 테스트:

```bash
uv run pytest tests/test_chart.py
uv run pytest tests/test_query.py
uv run pytest tests/test_storage.py
```

Lint:

```bash
uv run ruff check .
```

패키지 빌드:

```bash
uv run python -m build
```

## 테스트 원칙

- 단위 테스트는 실제 KIS API를 호출하지 않습니다.
- REST 응답은 mock payload로 검증합니다.
- 심볼 마스터 파서는 synthetic zip 데이터를 사용합니다.
- DuckDB 중복 방지와 deterministic query는 실제 임시 DB로 검증합니다.

## 보안 주의

이 프로젝트는 민감한 API 자격증명을 다룹니다.

- API key, app secret, 계좌번호, access token을 소스 코드에 저장하지 마세요.
- 실제 config, token cache, 로컬 DB/warehouse, 로그 파일을 커밋하지 마세요.
- CLI 출력이나 로그에 시크릿 원문을 노출하지 마세요.
- 주문/매매 기능은 현재 범위가 아니며 구현되어 있지 않습니다.
