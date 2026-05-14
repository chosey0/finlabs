# cli 패키지

`kis_cli.cli`는 Typer 기반 CLI 진입점입니다. 루트 앱은 `app.py`에 있으며, 로컬 개발에서는 `python -m kis_cli`로 실행합니다.

CLI 계층은 입력값 검증, 사용자 친화적 에러 변환, Rich 기반 출력, JSON/CSV 출력 및 파일 내보내기만 담당합니다. 인증, API 호출, 저장, 조회 같은 실제 작업은 `services/`, `core/`, `storage/`로 위임합니다.

## 모듈 구조

`app.py`는 루트 Typer 앱과 하위 앱 등록만 담당합니다. 명령 구현은 명령 그룹별 모듈에 둡니다.

```text
kis_cli/cli/
├── app.py       # 루트 Typer 앱 조립
├── common.py    # 공통 Console, 출력 포맷, CSV export helper
├── config.py    # python -m kis_cli config
├── auth.py      # python -m kis_cli auth
├── db.py        # python -m kis_cli db
├── symbols.py   # python -m kis_cli symbols
├── chart.py     # python -m kis_cli chart
├── query.py     # python -m kis_cli query
└── logs.py      # python -m kis_cli logs
```

새 명령을 추가할 때는 `app.py`에 command 함수를 직접 두지 않습니다. 기존 명령 그룹이면 해당 모듈에 추가하고, 새 그룹이면 새 `<group>.py`에서 `Typer` sub-app을 만든 뒤 `app.py`에 등록합니다. CLI 함수는 얇게 유지하고 비즈니스 로직은 서비스/코어/저장소 계층으로 위임합니다.

## config 명령

설정 파일과 프로필을 관리합니다.

```bash
python -m kis_cli config init
python -m kis_cli config init --profile mock --environment mock
python -m kis_cli config init --path ./config.yaml --force
```

```bash
python -m kis_cli config add
python -m kis_cli config validate
python -m kis_cli config validate --profile csq1404
python -m kis_cli config update --profile csq1404
python -m kis_cli config delete --profile csq1404 --yes
```

`config add`와 `config update`는 대화형 프롬프트를 사용합니다. 출력 시 API 키, 시크릿, 계좌번호는 마스킹됩니다.

## auth 명령

KIS REST 접근 토큰을 발급하거나 유효한 캐시 토큰을 재사용합니다.

```bash
python -m kis_cli auth test
python -m kis_cli auth test --profile csq1404
python -m kis_cli auth test --profile csq1404 --refresh
python -m kis_cli auth status
python -m kis_cli auth status --profile csq1404
python -m kis_cli auth status --all
python -m kis_cli auth clear --profile csq1404
python -m kis_cli auth clear --all
```

`auth test`는 토큰을 발급하거나 유효한 캐시 토큰을 재사용합니다. `auth status`는 KIS 서버에 요청하지 않고 로컬 캐시만 확인합니다. `auth clear`는 로컬 캐시 토큰을 삭제합니다.

토큰 값은 출력하지 않고, 발급/재사용 여부 또는 캐시 상태, 만료 시각, 남은 시간, 캐시 경로만 보여줍니다. 만료 시각은 KST 기준으로 표시됩니다.

`auth status` 상태값:

- `valid`: 캐시 토큰이 있고 만료 5분 전 기준으로 유효
- `expiring`: 캐시 토큰이 아직 만료되지 않았지만 5분 이내 만료
- `expired`: 캐시 토큰 만료
- `none`: 토큰 캐시 파일 없음
- `invalid`: 캐시 파일이 손상됐거나 프로필/환경과 맞지 않음

## db 명령

앱 SQLite DB와 시장 데이터용 DuckDB warehouse를 초기화하고, warehouse 구조와 레코드 수를 확인합니다. Supabase/PostgreSQL canonical store는 `--store supabase`로 스키마를 초기화합니다.

```bash
python -m kis_cli db init
python -m kis_cli db init --path ./warehouse.duckdb
python -m kis_cli db init --store supabase
```

`--store supabase`는 `KISCLI_SUPABASE_DB_DSN` 환경변수에서 PostgreSQL DSN을 읽고 `symbols`, `ohlcv_bars` 테이블과 조회용 인덱스를 생성합니다. DSN은 Supabase Dashboard의 Connection Method 중 **Transaction pooler** connection string을 사용합니다. 이 명령은 `--path`와 함께 사용할 수 없습니다.
환경변수가 없으면 CLI가 `profiles.env`에서 DSN을 찾고, 저장된 값도 없으면 비공개 입력으로 요청한 뒤 `profiles.env`에 저장해 이후 Supabase 명령에서 재사용합니다.

```bash
python -m kis_cli db schema
python -m kis_cli db schema --path ./warehouse.duckdb
```

`db schema`는 테이블별 컬럼, 타입, 필수 여부, PK 여부, 기본값, 인덱스 및 UNIQUE 여부를 출력합니다.

```bash
python -m kis_cli db counts
python -m kis_cli db counts --path ./warehouse.duckdb
```

`db counts`는 테이블별 `COUNT(*)`와 전체 합계를 출력합니다.

## logs 명령

앱 SQLite DB에 저장된 최근 작업 이력과 API 로그를 확인합니다.
`logs` 명령은 기존 app DB를 읽기만 하며, DB가 없으면 `python -m kis_cli db init`을 먼저 실행해야 합니다.

```bash
python -m kis_cli logs runs
python -m kis_cli logs runs --limit 50
python -m kis_cli logs runs --status failed
python -m kis_cli logs runs --kind symbols --market NASDAQ
python -m kis_cli logs runs --symbol AAPL --since 2026-05-08
python -m kis_cli logs runs --path ./app.db
```

```bash
python -m kis_cli logs api
python -m kis_cli logs api --limit 50
python -m kis_cli logs api --endpoint ohlcv
python -m kis_cli logs api --format json
python -m kis_cli logs api --format csv
python -m kis_cli logs api --path ./app.db
```

## symbols 명령

KIS 심볼 마스터 파일을 다운로드해 DuckDB warehouse 또는 Supabase/PostgreSQL에 저장하고, 저장된 심볼을 검색합니다.

```bash
python -m kis_cli symbols download --market NASDAQ
python -m kis_cli symbols download --market NYSE
python -m kis_cli symbols download --market NASDAQ
python -m kis_cli symbols download --all
python -m kis_cli symbols download --market NASDAQ --db-path ./warehouse.duckdb
python -m kis_cli symbols download --market NASDAQ --store supabase
```

```bash
python -m kis_cli symbols search --query apple
python -m kis_cli symbols search --query 삼성 --limit 10
python -m kis_cli symbols search --query apple --market NASDAQ
```

검색 결과는 query와 더 유사한 순서로 정렬됩니다. `Symbol` 오른쪽에는 실시간 구독 등에 사용할 수 있는 `Realtime symbol`도 출력됩니다. `--store supabase`는 `KISCLI_SUPABASE_DB_DSN`으로 연결한 Supabase/PostgreSQL `symbols` 테이블에 upsert합니다.
환경변수가 없고 `profiles.env`에도 값이 없으면 DSN을 비공개 입력으로 요청한 뒤 저장합니다.

## chart 명령

KIS REST OHLCV 이력을 수집합니다. `--save`를 주면 DuckDB warehouse 또는 Supabase/PostgreSQL의 `ohlcv_bars`에 시가/고가/저가/종가/거래량과 대비/등락률/거래대금을 중복 방지 insert로 저장합니다.

기본 사용은 기간 단위 명령을 권장합니다.

```bash
python -m kis_cli chart daily --profile csq1404 --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save
python -m kis_cli chart daily --profile csq1404 --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save --store supabase
python -m kis_cli chart weekly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07
python -m kis_cli chart monthly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07
python -m kis_cli chart yearly --profile csq1404 --symbol 005930 --start 2020-01-01 --end 2026-05-07
```

`history`는 `--period`를 직접 지정하는 고급/범용 명령입니다.

```bash
python -m kis_cli chart history --profile csq1404 --symbol 005930 --period D --start 2026-04-01 --end 2026-05-07 --save
python -m kis_cli chart history --profile csq1404 --symbol 005930 --period W --start 2025-01-01 --end 2026-05-07 --save
```

`chart` 명령은 로컬 DuckDB `symbols` 테이블에서 `--symbol`의 market을 해석합니다. 먼저 `python -m kis_cli symbols download`로 대상 시장의 심볼을 저장해두세요. `--save --store supabase`는 Supabase/PostgreSQL `ohlcv_bars` 테이블에 저장합니다. `--end`를 생략하면 오늘 날짜까지 조회합니다.
환경변수가 없고 `profiles.env`에도 값이 없으면 DSN을 비공개 입력으로 요청한 뒤 저장합니다.

해외 개별주식의 일/주/월 OHLCV는 `[해외주식] 해외주식 기간별시세` API(`/dailyprice`)를 사용합니다. 1회 최대 100건을 기준으로, 응답에 다음 `KEYB`가 있으면 같은 `BYMD`에서 다음 묶음을 이어 조회하고, `KEYB`가 없더라도 100건이 꽉 찬 응답이면 가장 오래된 응답일 이전으로 `BYMD`를 이동해 이어 조회합니다. 해외 개별주식 연봉(`Y`)은 지원하지 않습니다.

## query 명령

저장된 일봉 OHLCV를 조회하거나 내보냅니다. 현재는 `interval=1d`만 조회하며, `--market`과 `--interval` 옵션은 받지 않습니다. 출력과 export에는 대비, 등락률, 거래대금 컬럼도 포함됩니다.

```bash
python -m kis_cli query ohlcv --symbol AAPL
python -m kis_cli query ohlcv --symbol 005930 --start 2026-04-01 --end 2026-05-07
python -m kis_cli query ohlcv --symbol AAPL --limit 50
python -m kis_cli query ohlcv --symbol AAPL --all
```

기본 조회는 최신 20개 일봉을 반환합니다. `--all`을 사용하면 날짜 조건에 맞는 모든 일봉을 조회합니다. 조회 결과는 최신 날짜가 먼저 나옵니다.

출력 형식:

```bash
python -m kis_cli query ohlcv --symbol AAPL --format table
python -m kis_cli query ohlcv --symbol AAPL --format json
python -m kis_cli query ohlcv --symbol AAPL --format csv
```

table 출력은 `Change`, `Change Rate`, `Amount` 컬럼을 포함합니다. JSON/CSV 출력과 export는 다음 컬럼을 사용합니다.

```text
market,symbol,interval,timestamp,open,high,low,close,volume,change,change_rate,amount
```

내보내기:

```bash
python -m kis_cli query ohlcv --symbol AAPL --export ./exports/aapl.csv
python -m kis_cli query ohlcv --symbol AAPL --export ./exports/aapl.json
```

`--export`는 `.csv` 또는 `.json` 확장자를 기준으로 파일 형식을 결정합니다.
