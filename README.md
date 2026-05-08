# kis-cli

`kis-cli`는 Korea Investment & Securities Open API를 사용해 국내/해외 주식 시장 데이터를 수집하고 SQLite에 저장하는 Python CLI 프로젝트입니다. CLI 명령은 `kiscli`로 제공됩니다.

현재 구현 범위는 설정 관리, REST 인증 확인, 심볼 마스터 다운로드/검색, 현재가 조회, OHLCV 이력 수집/저장, 저장 데이터 조회/내보내기, SQLite DB 점검입니다.

이 프로젝트는 시장 데이터 수집용 CLI입니다. UI, 웹 대시보드, 차트 렌더링, 자동매매, 주문 실행, 전략/백테스트 기능은 포함하지 않습니다.

## 주요 기능

- 프로필 기반 설정 관리와 시크릿 분리 저장
- KIS REST access token 발급/캐시/검증
- KOSPI, KOSDAQ, 해외 시장 심볼 마스터 다운로드와 SQLite upsert
- 저장된 심볼 검색, query 유사도 기반 정렬, realtime symbol 출력
- 국내/해외 REST 현재가 조회
- 국내/해외 OHLCV 이력 수집
- `--save` 사용 시 `ohlcv_bars`에 중복 방지 저장
- 저장된 일봉 OHLCV 조회, table/json/csv 출력, csv/json export
- SQLite 스키마 생성, 구조 확인, 테이블별 레코드 수 확인

## 설치

개발 환경에서는 `uv` 사용을 권장합니다.

```bash
uv sync
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

## 빠른 시작

1. 설정 파일을 초기화합니다.

```bash
uv run kiscli config init
```

2. KIS API 프로필을 추가합니다.

```bash
uv run kiscli config add
```

3. 설정을 검증합니다.

```bash
uv run kiscli config validate --profile csq1404
```

4. REST 인증을 확인합니다.

```bash
uv run kiscli auth test --profile csq1404
uv run kiscli auth status --profile csq1404
```

5. DB를 초기화합니다.

```bash
uv run kiscli db init
```

6. 심볼 마스터를 다운로드합니다.

```bash
uv run kiscli symbols download --market KOSPI
uv run kiscli symbols download --market NASDAQ
```

7. OHLCV를 수집하고 저장합니다.

```bash
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
```

8. 저장된 일봉 데이터를 조회합니다.

```bash
uv run kiscli query ohlcv --symbol 005930
```

## 설정과 로컬 파일

기본 경로는 OS별 사용자 디렉터리를 사용합니다.

```text
Config: ~/.config/kis-cli/config.yaml
Secrets: ~/.config/kis-cli/profiles.env
Cache:  ~/.cache/kis-cli/
Data:   ~/.local/share/kis-cli/
DB:     ~/.local/share/kis-cli/kis-cli.db
```

API 키, API 시크릿, 계좌번호, 토큰은 패키지 소스 안에 저장하지 않습니다. CLI 출력에서도 민감 값은 마스킹합니다.

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
```

`--refresh`를 사용하면 유효한 캐시가 있어도 새 토큰을 요청합니다.

`auth status`는 KIS 서버에 요청하지 않고 로컬 토큰 캐시만 확인합니다. `--profile`을 생략하면 `active_profile`을 사용하고, `--all`은 모든 프로필의 토큰 상태를 보여줍니다. 상태값은 다음과 같습니다.

- `valid`: 캐시 토큰이 있고 만료 5분 전 기준으로 유효
- `expired`: 캐시 토큰이 만료됐거나 만료 임박
- `none`: 토큰 캐시 파일 없음
- `invalid`: 캐시 파일이 손상됐거나 프로필/환경과 맞지 않음

토큰 만료 시각은 CLI 출력에서 KST 기준으로 표시됩니다.

## DB 관리

SQLite 스키마 생성:

```bash
uv run kiscli db init
uv run kiscli db init --path ./kis-cli.db
```

DB 구조 확인:

```bash
uv run kiscli db schema
uv run kiscli db schema --path ./kis-cli.db
```

테이블별 레코드 수 확인:

```bash
uv run kiscli db counts
uv run kiscli db counts --path ./kis-cli.db
```

현재 주요 테이블은 다음과 같습니다.

- `symbols`
- `ohlcv_bars`
- `realtime_ticks`
- `api_logs`
- `ingest_runs`

중복 방지는 DB 제약조건으로 처리합니다.

```sql
UNIQUE (market, symbol)
UNIQUE (market, symbol, interval, timestamp)
UNIQUE (market, symbol, exchange_ts, seq)
```

## 심볼 마스터

심볼 마스터 다운로드:

```bash
uv run kiscli symbols download --market KOSPI
uv run kiscli symbols download --market KOSDAQ
uv run kiscli symbols download --market NASDAQ
uv run kiscli symbols download --all
```

커스텀 DB 경로:

```bash
uv run kiscli symbols download --market NASDAQ --db-path ./kis-cli.db
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

## 현재가 조회

국내 현재가:

```bash
uv run kiscli price current --profile csq1404 --market KOSPI --symbol 005930
```

해외 현재가:

```bash
uv run kiscli price current --profile csq1404 --market NASDAQ --symbol AAPL
```

출력 항목은 시장, 심볼, 이름, 현재가, 통화, 전일 대비, 등락률, 시가, 고가, 저가, 거래량입니다.

## OHLCV 수집

일봉 수집:

```bash
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07
```

저장까지 수행:

```bash
uv run kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
uv run kiscli chart daily --profile csq1404 --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save
```

기간 단위 명령:

```bash
uv run kiscli chart weekly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07 --save
uv run kiscli chart monthly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07 --save
uv run kiscli chart yearly --profile csq1404 --symbol 005930 --start 2020-01-01 --end 2026-05-07 --save
```

범용 history 명령:

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

## 저장 데이터 조회와 내보내기

현재 저장 데이터 조회는 일봉(`interval=1d`) 전용입니다. `--market`과 `--interval`은 받지 않고 `--symbol`만 사용합니다.

기본 조회:

```bash
uv run kiscli query ohlcv --symbol AAPL
uv run kiscli query ohlcv --symbol 005930 --limit 30
```

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
market,symbol,interval,timestamp,open,high,low,close,volume
```

## 패키지 구조

```text
kis_cli/
├── cli/       # Typer CLI, Rich 출력, JSON/CSV export
├── config/    # 설정 파일, 프로필, 시크릿 참조 해석
├── core/      # KIS REST 인증/클라이언트/현재가/OHLCV/심볼 파서
├── services/  # CLI 유즈케이스 조립
└── storage/   # SQLite 스키마, repository, DB 점검
```

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

패키지 빌드:

```bash
uv run python -m build
```

## 테스트 원칙

- 단위 테스트는 실제 KIS API를 호출하지 않습니다.
- REST 응답은 mock payload로 검증합니다.
- 심볼 마스터 파서는 synthetic zip 데이터를 사용합니다.
- SQLite 중복 방지와 deterministic query는 실제 임시 DB로 검증합니다.

## 보안 주의

이 프로젝트는 민감한 API 자격증명을 다룹니다.

- API key, app secret, 계좌번호, access token을 소스 코드에 저장하지 마세요.
- 실제 config, token cache, SQLite DB, 로그 파일을 커밋하지 마세요.
- CLI 출력이나 로그에 시크릿 원문을 노출하지 마세요.
- 주문/매매 기능은 현재 범위가 아니며 구현되어 있지 않습니다.
