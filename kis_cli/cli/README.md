# cli 패키지

`kis_cli.cli`는 Typer 기반 CLI 진입점입니다. 루트 앱은 `app.py`에 있으며, `pyproject.toml`의 엔트리포인트는 `kiscli = "kis_cli.cli.app:main"`입니다.

CLI 계층은 입력값 검증, 사용자 친화적 에러 변환, Rich 기반 출력, JSON/CSV 출력 및 파일 내보내기만 담당합니다. 인증, API 호출, 저장, 조회 같은 실제 작업은 `services/`, `core/`, `storage/`로 위임합니다.

## config 명령

설정 파일과 프로필을 관리합니다.

```bash
kiscli config init
kiscli config init --profile mock --environment mock
kiscli config init --path ./config.yaml --force
```

```bash
kiscli config add
kiscli config validate
kiscli config validate --profile csq1404
kiscli config update --profile csq1404
kiscli config delete --profile csq1404 --yes
```

`config add`와 `config update`는 대화형 프롬프트를 사용합니다. 출력 시 API 키, 시크릿, 계좌번호는 마스킹됩니다.

## auth 명령

KIS REST 접근 토큰을 발급하거나 유효한 캐시 토큰을 재사용합니다.

```bash
kiscli auth test
kiscli auth test --profile csq1404
kiscli auth test --profile csq1404 --refresh
```

토큰 값은 출력하지 않고, 발급/재사용 여부와 만료 시각, 캐시 경로만 보여줍니다.

## db 명령

SQLite DB를 초기화하고 구조와 레코드 수를 확인합니다.

```bash
kiscli db init
kiscli db init --path ./kis-cli.db
```

```bash
kiscli db schema
kiscli db schema --path ./kis-cli.db
```

`db schema`는 테이블별 컬럼, 타입, 필수 여부, PK 여부, 기본값, 인덱스 및 UNIQUE 여부를 출력합니다.

```bash
kiscli db counts
kiscli db counts --path ./kis-cli.db
```

`db counts`는 테이블별 `COUNT(*)`와 전체 합계를 출력합니다.

## symbols 명령

KIS 심볼 마스터 파일을 다운로드해 SQLite에 저장하고, 저장된 심볼을 검색합니다.

```bash
kiscli symbols download --market KOSPI
kiscli symbols download --market KOSDAQ
kiscli symbols download --market NASDAQ
kiscli symbols download --all
kiscli symbols download --market NASDAQ --db-path ./kis-cli.db
```

```bash
kiscli symbols search --query apple
kiscli symbols search --query 삼성 --limit 10
kiscli symbols search --query apple --market NASDAQ
```

검색 결과는 query와 더 유사한 순서로 정렬됩니다. `Symbol` 오른쪽에는 실시간 구독 등에 사용할 수 있는 `Realtime symbol`도 출력됩니다.

## price 명령

KIS REST 현재가를 조회합니다.

```bash
kiscli price current --profile csq1404 --market KOSPI --symbol 005930
kiscli price current --profile csq1404 --market NASDAQ --symbol AAPL
```

출력 항목은 시장, 심볼, 이름, 현재가, 통화, 전일 대비, 등락률, 시가, 고가, 저가, 거래량입니다.

## chart 명령

KIS REST OHLCV 이력을 수집합니다. `--save`를 주면 `ohlcv_bars`에 `INSERT OR IGNORE`로 저장합니다.

```bash
kiscli chart history --profile csq1404 --market KOSPI --symbol 005930 --period D --start 2026-04-01 --end 2026-05-07 --save
kiscli chart history --profile csq1404 --market KOSPI --symbol 005930 --period W --start 2025-01-01 --end 2026-05-07 --save
```

편의 명령도 제공합니다.

```bash
kiscli chart daily --profile csq1404 --market NASDAQ --symbol AAPL --start 2026-04-01 --end 2026-05-07 --save
kiscli chart weekly --profile csq1404 --market KOSPI --symbol 005930 --start 2025-01-01 --end 2026-05-07
kiscli chart monthly --profile csq1404 --market KOSPI --symbol 005930 --start 2025-01-01 --end 2026-05-07
kiscli chart yearly --profile csq1404 --market KOSPI --symbol 005930 --start 2020-01-01 --end 2026-05-07
```

국내 OHLCV는 응답 제한에 맞춰 가장 오래된 수집일 이전 구간을 이어 조회합니다. 해외 개별주식의 일/주/월 OHLCV는 `[해외주식] 해외주식 기간별시세` API(`/dailyprice`)를 사용합니다. 1회 최대 100건을 기준으로, 응답에 다음 `KEYB`가 있으면 같은 `BYMD`에서 다음 묶음을 이어 조회하고, `KEYB`가 없더라도 100건이 꽉 찬 응답이면 가장 오래된 응답일 이전으로 `BYMD`를 이동해 이어 조회합니다. 해외 개별주식 연봉(`Y`)은 지원하지 않습니다.

## query 명령

저장된 일봉 OHLCV를 조회하거나 내보냅니다. 현재는 `interval=1d`만 조회하며, `--market`과 `--interval` 옵션은 받지 않습니다.

```bash
kiscli query ohlcv --symbol AAPL
kiscli query ohlcv --symbol 005930 --start 2026-04-01 --end 2026-05-07
kiscli query ohlcv --symbol AAPL --limit 50
```

출력 형식:

```bash
kiscli query ohlcv --symbol AAPL --format table
kiscli query ohlcv --symbol AAPL --format json
kiscli query ohlcv --symbol AAPL --format csv
```

내보내기:

```bash
kiscli query ohlcv --symbol AAPL --export ./exports/aapl.csv
kiscli query ohlcv --symbol AAPL --export ./exports/aapl.json
```

`--export`는 `.csv` 또는 `.json` 확장자를 기준으로 파일 형식을 결정합니다.
