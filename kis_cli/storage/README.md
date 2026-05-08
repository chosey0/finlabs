# storage 패키지

`kis_cli.storage`는 앱 메타데이터용 SQLite DB와 시장 데이터용 DuckDB warehouse를 분리한 저장 계층입니다. DB 연결, 스키마 생성, 중복 방지, deterministic query, DB 구조/레코드 수 확인을 담당합니다.

## 기본 DB 경로

기본 DB 파일은 사용자 데이터 디렉터리에 생성됩니다.

```text
~/.local/share/kis-cli/app.db
~/.local/share/kis-cli/warehouse.duckdb
```

CLI에서 다른 파일을 사용하려면 `--path` 또는 `--db-path`를 지정합니다.

```bash
kiscli db init --path ./warehouse.duckdb
kiscli symbols download --market NASDAQ --db-path ./warehouse.duckdb
kiscli query ohlcv --symbol AAPL --db-path ./warehouse.duckdb
```

## DB 초기화

`init_database()`는 부모 디렉터리를 만들고 스키마를 생성합니다.

```bash
kiscli db init
kiscli db init --path ./warehouse.duckdb
```

DuckDB warehouse 테이블:

- `symbols`
- `ohlcv_bars`
- `realtime_ticks`

SQLite app DB 테이블:

- `api_logs`
- `ingest_runs`

`symbols download`와 `chart ... --save`는 `ingest_runs`에 시작/종료 상태와 저장 건수를 기록하고, 관련 요청 결과는 `api_logs`에 기록합니다. 저장되는 시각 값은 KST ISO 형식입니다.

## 스키마

`warehouse.py`는 시장 데이터용 DuckDB 스키마를 정의하고, `app_db.py`는 앱 내부 상태용 SQLite 스키마를 정의합니다.

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
kiscli db schema
kiscli db schema --path ./warehouse.duckdb
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

DB 파일이 없으면 새로 만들지 않고 `kiscli db init`을 먼저 실행하라는 에러를 냅니다.

## 레코드 수 확인

`inspect_database_counts()`는 테이블별 `COUNT(*)`와 전체 합계를 반환합니다.

```bash
kiscli db counts
kiscli db counts --path ./warehouse.duckdb
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
kiscli query ohlcv --symbol AAPL
kiscli query ohlcv --symbol AAPL --start 2026-04-01 --end 2026-05-07
kiscli query ohlcv --symbol AAPL --format csv
kiscli query ohlcv --symbol AAPL --export ./exports/aapl.json
```

CSV/JSON 컬럼은 다음 순서를 사용합니다.

```text
market,symbol,interval,timestamp,open,high,low,close,volume
```
