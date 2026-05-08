# services 패키지

`kis_cli.services`는 CLI에서 받은 요청을 실제 작업 단위로 조립하는 계층입니다. 설정 해석, 토큰 확보, core API 호출, storage 저장/조회 흐름을 연결합니다.

CLI 파일은 얇게 유지하고, 사용자 관점의 기능 흐름은 이 패키지에 둡니다.

## 인증 서비스

`auth.py`는 프로필을 해석하고 REST 토큰을 발급 또는 재사용합니다.

주요 함수:

```python
from kis_cli.services.auth import get_auth_statuses, get_rest_token, test_auth
```

동작:

- `resolve_profile()`로 설정을 해석
- 유효한 캐시 토큰이 있으면 재사용
- `--refresh` 또는 캐시 만료 시 KIS 토큰 발급
- `get_auth_statuses()`로 KIS 서버 요청 없이 캐시 상태 확인
- 토큰은 캐시 파일에 저장하고 CLI에는 원문을 출력하지 않음
- CLI 만료 시각은 KST 기준으로 표시

CLI 예:

```bash
kiscli auth test --profile csq1404
kiscli auth test --profile csq1404 --refresh
kiscli auth status --profile csq1404
kiscli auth status --all
```

## 현재가 서비스

`price.py`는 현재가 조회 유즈케이스입니다.

주요 함수:

```python
from kis_cli.services.price import get_current_price
```

동작:

1. 프로필 해석
2. REST 토큰 확보
3. `KisClient` 생성
4. `core.price.inquire_current_price()` 호출

CLI 예:

```bash
kiscli price current --profile csq1404 --market KOSPI --symbol 005930
kiscli price current --profile csq1404 --market NASDAQ --symbol AAPL
```

## 차트/OHLCV 서비스

`chart.py`는 국내/해외 OHLCV 이력 수집과 선택 저장을 담당합니다.

주요 함수:

```python
from kis_cli.services.chart import collect_ohlcv_history
```

동작:

1. 프로필 해석
2. REST 토큰 확보
3. KIS OHLCV 이력 조회
4. `--save`가 있으면 SQLite DB 초기화 후 `ohlcv_bars`에 저장
5. 저장은 `INSERT OR IGNORE` 기반으로 중복을 방지

저장 interval:

```text
D -> 1d
W -> 1w
M -> 1mo
Y -> 1y
```

CLI 예:

```bash
kiscli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
kiscli chart weekly --profile csq1404 --symbol 005930 --start 2025-01-01 --end 2026-05-07 --save
kiscli chart history --profile csq1404 --symbol AAPL --period D --start 2026-04-01 --end 2026-05-07 --save
```

`chart` 서비스는 `symbols` 테이블에서 `symbol`의 market을 해석합니다. `end`가 비어 있으면 오늘 날짜를 종료일로 사용합니다.

## 심볼 서비스

`symbols.py`는 심볼 마스터 다운로드/저장/검색 유즈케이스를 제공합니다.

주요 함수:

```python
from kis_cli.services.symbols import download_and_store_symbols, search_stored_symbols
```

동작:

- `download_and_store_symbols()`: 시장 정규화, DB 초기화, 심볼 마스터 다운로드, 파싱 결과 upsert
- `search_stored_symbols()`: 저장된 심볼을 symbol/한글명/영문명 기준으로 검색

CLI 예:

```bash
kiscli symbols download --market KOSPI
kiscli symbols download --market NASDAQ --db-path ./kis-cli.db
kiscli symbols search --query apple
kiscli symbols search --query 삼성 --limit 10
```

## 저장 데이터 조회 서비스

`query.py`는 저장된 일봉 OHLCV 조회 유즈케이스입니다.

주요 함수:

```python
from kis_cli.services.query import query_stored_daily_ohlcv
```

제약:

- `symbol`만 입력받아 조회
- `market` 인자는 사용하지 않음
- `interval`은 내부적으로 항상 `1d`
- `start`, `end`, `limit` 지원

CLI 예:

```bash
kiscli query ohlcv --symbol AAPL
kiscli query ohlcv --symbol AAPL --start 2026-04-01 --end 2026-05-07
kiscli query ohlcv --symbol AAPL --format json
kiscli query ohlcv --symbol AAPL --export ./exports/aapl.csv
```

파일 내보내기 자체는 CLI 출력 계층에서 처리하고, 서비스는 조회 결과를 dict 목록으로 반환합니다.
