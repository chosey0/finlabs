# storage 패키지

`kis_cli.storage`는 앱 메타데이터용 SQLite DB, 로컬 시장 데이터용 DuckDB, 원격 canonical store용 Supabase/PostgreSQL 스키마를 분리한 저장 계층입니다. DB 연결, 스키마 생성, 중복 방지, deterministic query, DB 구조/레코드 수 확인을 담당합니다.

## 기본 DB 경로

기본 DB 파일은 사용자 데이터 디렉터리에 생성됩니다.

```text
~/.local/share/kis-cli/app.db
~/.local/share/kis-cli/warehouse.duckdb
```

CLI에서 다른 파일을 사용하려면 `--path` 또는 `--db-path`를 지정합니다.

```bash
python -m kis_cli db init --path ./warehouse.duckdb
python -m kis_cli symbols download --market NASDAQ --db-path ./warehouse.duckdb
python -m kis_cli query ohlcv --symbol AAPL --db-path ./warehouse.duckdb
```

Supabase/PostgreSQL canonical store는 파일 경로 대신 DSN 환경변수를 사용합니다.
DSN은 Supabase Dashboard의 Connection Method 중 **Transaction pooler** connection string을 사용합니다.

```bash
export KISCLI_SUPABASE_DB_DSN='postgresql://USER:PASSWORD@HOST:6543/postgres'
python -m kis_cli db init --store supabase
python -m kis_cli symbols download --market NASDAQ --store supabase
python -m kis_cli chart daily --profile csq1404 --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save --store supabase
```

## DB 초기화

`init_database()`는 부모 디렉터리를 만들고 스키마를 생성합니다.

```bash
python -m kis_cli db init
python -m kis_cli db init --path ./warehouse.duckdb
python -m kis_cli db init --store supabase
```

DuckDB warehouse 테이블:

- `symbols`
- `ohlcv_bars`
- `realtime_ticks`

SQLite app DB 테이블:

- `api_logs`
- `ingest_runs`

`symbols download`와 `chart ... --save`는 `ingest_runs`에 시작/종료 상태와 저장 건수를 기록하고, 관련 요청 결과는 `api_logs`에 기록합니다. 저장되는 시각 값은 KST ISO 형식입니다.

## 저장소 역할

권장 역할은 다음과 같습니다.

```text
SQLite app DB          # FinLabs CLI 내부 실행 상태와 로컬 작업/API 로그
Supabase/PostgreSQL    # symbols, ohlcv_bars 원천 시장 데이터 canonical store
DuckDB                 # 로컬 분석 mart, feature engineering, 학습용 snapshot/export
```

Supabase/PostgreSQL 연결정보는 `KISCLI_SUPABASE_DB_DSN` 환경변수 또는 사용자 config 디렉터리의 `profiles.env`에서 읽습니다. DSN은 Supabase Dashboard의 Connection Method 중 **Transaction pooler** connection string을 사용합니다. 1차 Supabase 저장 대상은 `symbols`, `ohlcv_bars`입니다. WebSocket 실시간 데이터용 `realtime_ticks`는 아직 Supabase 범위에 포함하지 않습니다.
CLI에서 `--store supabase`를 실행할 때 환경변수가 없으면 `profiles.env`에서 DSN을 찾고, 저장된 값도 없으면 비공개 입력으로 요청한 뒤 `profiles.env`에 저장해 이후 Supabase 명령에서 재사용합니다.
URL 형태의 DSN은 연결 직전에 username/password를 URL encoding하므로 password에 `!@#$` 같은 특수문자가 포함되어도 그대로 입력할 수 있습니다.

## 스키마

`warehouse.py`는 시장 데이터용 DuckDB 스키마를 정의하고, `supabase_schema.py`는 Supabase/PostgreSQL canonical store 스키마를 정의합니다. `supabase.py`는 PostgreSQL DSN 연결, schema init, `symbols` upsert, `ohlcv_bars` 중복 방지 insert를 담당합니다. `app_db.py`는 앱 내부 상태용 SQLite 스키마를 정의합니다.

Supabase/PostgreSQL canonical store 테이블:

- `symbols`
- `ohlcv_bars`

Supabase/PostgreSQL에서는 날짜/시각 타입을 명확히 사용합니다.

- `symbols.listed_date`: `DATE`
- `symbols.downloaded_at`: `TIMESTAMPTZ`
- `ohlcv_bars.trade_date`: `DATE`
- `ohlcv_bars.fetched_at`: `TIMESTAMPTZ`

DuckDB의 `ohlcv_bars.timestamp`는 Supabase/PostgreSQL에서 `trade_date`로 대응합니다.

### symbols

심볼 마스터 저장 테이블입니다.

주요 컬럼:

- `market`
- `symbol`
- `standard_code`
- `realtime_symbol`
- `korean_name`
- `english_name`
- `security_type`
- `currency`
- `exchange_id`
- `exchange_code`
- `exchange_name`
- `country_code`
- `listed_date`
- `base_price`
- `lot_size`
- `raw_source`
- `raw`
- `downloaded_at`
- `created_at`
- `updated_at`

중복 방지:

```sql
UNIQUE (market, symbol)
```

Supabase/PostgreSQL에서는 `PRIMARY KEY (market, symbol)`을 사용합니다.

### ohlcv_bars

OHLCV 저장 테이블입니다. 기본 OHLCV 값과 KIS 응답의 대비, 등락률, 거래대금을 함께 저장합니다.

주요 컬럼:

- `market`
- `symbol`
- `interval`
- `timestamp`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `change`
- `change_rate`
- `amount`

중복 방지:

```sql
UNIQUE (market, symbol, interval, timestamp)
```

Supabase/PostgreSQL에서는 `PRIMARY KEY (market, symbol, interval, trade_date)`를 사용합니다.

### realtime_ticks

실시간 체결 저장을 위한 테이블입니다.

주요 컬럼:

- `market`
- `symbol`
- `exchange_ts`
- `received_at`
- `received_seq`
- `seq`
- `price`
- `volume`

중복 방지:

```sql
UNIQUE (market, symbol, exchange_ts, seq)
```

## Repository 함수

`repositories.py`는 DB 접근 함수를 제공합니다.

심볼:

```python
insert_symbol(connection, market="NASDAQ", symbol="AAPL", name="Apple Inc.")
upsert_symbols(connection, records)
search_symbols(connection, query="apple", market="NASDAQ", limit=20)
```

`search_symbols()`는 query와 더 유사한 결과가 먼저 나오도록 정렬합니다.

OHLCV:

```python
insert_ohlcv_bar(
    connection,
    market="NASDAQ",
    symbol="AAPL",
    interval="1d",
    timestamp="2026-05-07",
    open=100.0,
    high=110.0,
    low=99.0,
    close=105.0,
    volume=1000,
)
insert_ohlcv_bars(connection, records)
list_ohlcv_bars(connection, market="NASDAQ", symbol="AAPL", interval="1d")
query_daily_ohlcv_bars(connection, symbol="AAPL", start="2026-04-01", end="2026-05-07")
```

`query_daily_ohlcv_bars()`는 `interval='1d'`만 조회합니다. 결과는 최신 날짜가 먼저 나오도록 정렬합니다.
`insert_ohlcv_bars()`는 임시 CSV와 DuckDB `COPY`를 사용해 bulk insert를 수행하고, 이미 존재하는 `(market, symbol, interval, timestamp)` 행은 건너뜁니다.
`insert_supabase_ohlcv_bars()`는 Supabase/PostgreSQL의 `(market, symbol, interval, trade_date)` primary key에 대해 `ON CONFLICT DO NOTHING`으로 중복을 방지합니다.

실시간 tick:

```python
insert_realtime_tick(
    connection,
    market="KOSPI",
    symbol="005930",
    exchange_ts="2026-05-07T09:00:00Z",
    received_at="2026-05-07T09:00:01Z",
    received_seq=1,
    seq=42,
    price=70500.0,
    volume=10,
)
```

## DB 구조 확인

`inspect_database_schema()`는 테이블, 컬럼, 인덱스 정보를 반환합니다.

```bash
python -m kis_cli db schema
python -m kis_cli db schema --path ./warehouse.duckdb
```

출력 정보:

- 테이블명
- 컬럼명
- 타입
- NOT NULL 여부
- PK 여부
- 기본값
- 인덱스명
- UNIQUE 여부
- 인덱스 컬럼

DB 파일이 없으면 새로 만들지 않고 `python -m kis_cli db init`을 먼저 실행하라는 에러를 냅니다.

## 레코드 수 확인

`inspect_database_counts()`는 테이블별 `COUNT(*)`와 전체 합계를 반환합니다.

```bash
python -m kis_cli db counts
python -m kis_cli db counts --path ./warehouse.duckdb
```

예상 출력 항목:

```text
symbols        3000
ohlcv_bars     250
realtime_ticks   0
Total         3250
```

## 저장 데이터 조회/내보내기

저장된 일봉 OHLCV는 `query` 명령으로 조회합니다.

```bash
python -m kis_cli query ohlcv --symbol AAPL
python -m kis_cli query ohlcv --symbol AAPL --start 2026-04-01 --end 2026-05-07
python -m kis_cli query ohlcv --symbol AAPL --format csv
python -m kis_cli query ohlcv --symbol AAPL --export ./exports/aapl.json
```

CSV/JSON 컬럼은 다음 순서를 사용합니다.

```text
market,symbol,interval,timestamp,open,high,low,close,volume,change,change_rate,amount
```
