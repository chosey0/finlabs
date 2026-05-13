# core 패키지

`kis_cli.core`는 KIS Open API와 직접 맞닿는 계층입니다. REST 엔드포인트, 인증 요청, 공통 REST 클라이언트, 현재가/OHLCV 파서, 심볼 마스터 다운로드/파싱을 담당합니다.

API 세부 필드와 TR ID는 `.agents/kis-skill/resources/*.xlsx` 문서를 기준으로 유지해야 합니다. 구현 시 추측으로 URL, TR ID, 요청/응답 필드를 추가하지 않습니다.

## 엔드포인트와 도메인

`endpoints.py`는 환경별 기본 도메인과 토큰 경로를 제공합니다.

```text
real: https://openapi.koreainvestment.com:9443
mock: https://openapivts.koreainvestment.com:29443
token path: /oauth2/tokenP
```

사용 예:

```python
from kis_cli.core.endpoints import base_url, token_url

base_url("real")
token_url("mock")
```

## REST 인증

`auth.py`는 REST access token 발급을 담당합니다.

- `issue_access_token(environment, app_key, app_secret)`
- `parse_token_response(payload, issued_at=...)`
- 인증 실패 시 `KisAuthError`

CLI에서는 다음 명령을 통해 사용됩니다.

```bash
python -m kis_cli auth test --profile csq1404
python -m kis_cli auth test --profile csq1404 --refresh
python -m kis_cli auth status --profile csq1404
python -m kis_cli auth status --all
python -m kis_cli auth clear --profile csq1404
```

토큰 값은 출력하지 않습니다. CLI에 표시되는 토큰 만료 시각은 KST 기준입니다.

## 토큰 캐시

`token_cache.py`는 발급된 REST 토큰을 사용자 캐시 디렉터리에 저장하고 재사용합니다.

- 캐시 경로: `~/.cache/kis-cli/tokens/{profile_id}.json`
- 만료 5분 전부터 유효하지 않은 것으로 판단
- 토큰 파일은 임시 파일에 쓴 뒤 원자적으로 교체
- 손상된 캐시는 `invalid`로 구분
- `auth status`는 캐시 파일만 읽어서 `valid`, `expiring`, `expired`, `none`, `invalid` 상태를 표시

주요 함수:

```python
from kis_cli.core.token_cache import read_cached_token, write_cached_token, clear_cached_token
```

## 공통 REST 클라이언트

`client.py`의 `KisClient`는 인증된 GET 요청을 보냅니다.

- `authorization`
- `appKey`
- `appSecret`
- `tr_id`
- `tr_cont`
- `custtype`

KIS 응답의 `rt_cd`가 `0`이 아니면 `KisApiError`를 발생시킵니다. 응답 헤더까지 필요한 API는 `get_response()`를 사용할 수 있습니다.

## 현재가 조회

`price.py`는 국내/해외 현재가 조회와 응답 정규화를 담당합니다.

국내 현재가:

- Path: `/uapi/domestic-stock/v1/quotations/inquire-price`
- TR ID: `FHKST01010100`
- 주요 파라미터: `FID_COND_MRKT_DIV_CODE=J`, `FID_INPUT_ISCD`

해외 현재가:

- Path: `/uapi/overseas-price/v1/quotations/price`
- TR ID: `HHDFS00000300`
- 주요 파라미터: `EXCD`, `SYMB`

정규화 결과는 `CurrentPrice`로 반환됩니다.

## OHLCV 이력 조회

`chart.py`는 국내/해외 OHLCV 이력 조회, 연속 조회, 파싱을 담당합니다.

지원 period:

```text
D -> 1d
W -> 1w
M -> 1mo
Y -> 1y
```

국내 OHLCV:

- Path: `/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice`
- TR ID: `FHKST03010100`
- 응답 제한에 맞춰 가장 오래된 수집일 이전 구간을 이어 조회

해외 개별주식 OHLCV:

- Path: `/uapi/overseas-price/v1/quotations/dailyprice`
- TR ID: `HHDFS76240000`
- 지원 period: `D`, `W`, `M`
- 요청의 `GUBN`은 `D=0`, `W=1`, `M=2`로 변환
- 1회 최대 100건 기준으로 조회
- 응답에 다음 `KEYB`가 있으면 같은 `BYMD`에서 다음 묶음을 이어 조회
- `KEYB`가 없더라도 100건이 꽉 찬 응답이면 가장 오래된 응답일 이전으로 `BYMD`를 이동해 이어 조회
- 해외 개별주식 `Y`는 지원하지 않음

해외 지수/환율/특수 상품 OHLCV:

- Path: `/uapi/overseas-price/v1/quotations/inquire-daily-chartprice`
- TR ID: `FHKST03030100`
- 지원 period: `D`, `W`, `M`, `Y`

CLI 예:

```bash
python -m kis_cli chart daily --profile csq1404 --symbol 005930 --start 2026-04-01 --end 2026-05-07 --save
python -m kis_cli chart history --profile csq1404 --symbol 005930 --period W --start 2025-01-01 --end 2026-05-07
```

정규화 결과는 `OhlcvBar`이며, 시가/고가/저가/종가/거래량과 함께 KIS 응답의 대비, 등락률, 거래대금을 담습니다. 저장 시 `bar_to_db_values()`로 warehouse 저장 형태로 변환합니다.

## 심볼 마스터

`symbol_master.py`는 KIS/DWS 심볼 마스터 zip 파일을 다운로드하고 정규화합니다.

지원 시장:

```text
KOSPI, KOSDAQ, NASDAQ, NYSE, AMEX,
SHANGHAI, SHANGHAI_INDEX, SHENZHEN, SHENZHEN_INDEX,
TOKYO, HONGKONG, HANOI, HOCHIMINH
```

국내는 fixed-width `.mst`, 해외는 tab-separated `.cod`를 파싱합니다.

CLI 예:

```bash
python -m kis_cli symbols download --market KOSPI
python -m kis_cli symbols download --market NASDAQ
python -m kis_cli symbols download --all
```

검색과 저장은 `services.symbols`와 `storage.repositories`에서 이어 처리합니다.
