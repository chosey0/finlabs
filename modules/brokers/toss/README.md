<div align="center">

# FinLabs Toss Securities SDK

**토스증권 Open API의 인증과 읽기 전용 시장 데이터를 제공하는 비동기 Python SDK**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![HTTPX](https://img.shields.io/badge/HTTPX-0.27+-2F6F9F?style=for-the-badge)](https://www.python-httpx.org/)
[![OAuth2](https://img.shields.io/badge/OAuth_2.0-Client_Credentials-EB5424?style=for-the-badge)](https://developers.tossinvest.com/docs)
[![Tests](https://img.shields.io/badge/Tests-7_Passing-00C853?style=for-the-badge&logo=pytest&logoColor=white)](../../../tests/brokers/toss/test_toss_sdk.py)

OAuth2 토큰 발급부터 현재가, 1분봉·일봉, 종목 기본정보 조회까지 **타입이 지정된 비동기 인터페이스**로 제공합니다.

[FinLabs](../../../README.md) · [토스증권 API 문서](https://developers.tossinvest.com/docs) · [회귀 테스트](../../../tests/brokers/toss/test_toss_sdk.py)

</div>

---

## Overview

`modules/brokers/toss`는 토스증권 Open API를 감싸는 독립적인 Python SDK입니다. OAuth 2.0 Client Credentials Grant로 액세스 토큰을 발급하고, 토큰을 메모리에 캐시한 뒤 REST API 요청에 자동으로 적용합니다.

이 패키지는 FinLabs의 저장소, CLI, 오케스트레이션 계층에 의존하지 않습니다. API 전송과 응답 파싱만 담당하며, 금액과 가격은 `Decimal`, 날짜와 시각은 표준 `date`·`datetime`, 응답 모델은 frozen dataclass로 반환합니다.

---

## Features

| | 기능 | 설명 |
|---|------|------|
| **[OAuth2 인증]** | Client Credentials Grant | `client_id`와 `client_secret`으로 액세스 토큰 발급 |
| **[토큰 캐시]** | 메모리 기반 재사용 | 만료 전 토큰을 재사용하고 만료가 가까우면 자동 재발급 |
| **[현재가 조회]** | 국내·미국 주식 다건 조회 | 최대 200개 심볼을 한 요청으로 조회하고 `CurrentPrice`로 변환 |
| **[캔들 조회]** | 1분봉·일봉 | `1m`, `1d` 간격과 `before` 기반 페이지네이션 지원 |
| **[종목 정보]** | 종목 마스터 조회 | 시장, 통화, 상장 상태, 발행주식수와 국내 시장 상세정보 제공 |
| **[오류 모델]** | API 오류 보존 | HTTP 상태, 오류 코드, 요청 ID, 해결 힌트와 재시도 시간을 예외에 보존 |
| **[Rate Limit 대응]** | 429 자동 재시도 | `Retry-After` 헤더를 우선 사용하고 제한 횟수까지 백오프 재시도 |
| **[입력 검증]** | 심볼·개수·간격 검증 | API 호출 전에 심볼 형식, 최대 개수, 캔들 범위를 검증 |

---

## Request Flow

```text
TossClient
    │
    ├── ensure_token
    │     Client Credentials → access token → MemoryTokenCache
    │
    ▼
MarketDataAPI / StocksAPI
    │  Authorization: Bearer {access_token}
    ▼
AsyncHttpTransport
    │  HTTPX request → error envelope / rate-limit handling
    ▼
parsers
    │  JSON → Decimal · datetime · frozen dataclass
    ▼
CurrentPrice / CandlePage / StockInfo
```

---

## Tech Stack

### Runtime

![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![HTTPX](https://img.shields.io/badge/HTTPX-0.27+-2F6F9F?style=flat-square)
![asyncio](https://img.shields.io/badge/asyncio-stdlib-3776AB?style=flat-square&logo=python&logoColor=white)
![OAuth2](https://img.shields.io/badge/OAuth_2.0-Client_Credentials-EB5424?style=flat-square)

### Models & Quality

![dataclasses](https://img.shields.io/badge/dataclasses-frozen-4B8BBE?style=flat-square)
![Decimal](https://img.shields.io/badge/Decimal-Exact_Pricing-4B8BBE?style=flat-square)
![pytest](https://img.shields.io/badge/pytest-9.0+-0A9EDC?style=flat-square&logo=pytest&logoColor=white)
![Ruff](https://img.shields.io/badge/Ruff-0.15+-D7FF64?style=flat-square&logo=ruff&logoColor=black)

---

## API Coverage

| SDK 메서드 | Open API 엔드포인트 | 반환 모델 | 상태 |
|------------|---------------------|-----------|:----:|
| `client.ensure_token()` | `POST /oauth2/token` | `str` | 구현 |
| `client.market.prices()` | `GET /api/v1/prices` | `tuple[CurrentPrice, ...]` | 구현 |
| `client.market.candles()` | `GET /api/v1/candles` | `CandlePage` | 구현 |
| `client.stocks.get()` | `GET /api/v1/stocks` | `tuple[StockInfo, ...]` | 구현 |

호가, 최근 체결, 상·하한가, 종목 경고, 환율, 시장 캘린더는 토스증권 Open API에 존재하지만 아직 이 SDK의 공개 메서드로 구현되지 않았습니다.

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv`
- 토스증권 WTS에서 발급한 Open API `client_id`와 `client_secret`

### 설치

저장소 루트에서 의존성을 동기화합니다.

```bash
git clone https://github.com/chosey0/finlabs.git
cd finlabs
uv sync
```

### 환경 변수 설정

자격증명은 소스나 설정 파일에 저장하지 않고 실행 환경에서 주입합니다.

```bash
export TOSS_CLIENT_ID="your-client-id"
export TOSS_CLIENT_SECRET="your-client-secret"
```

PowerShell에서는 다음과 같이 설정합니다.

```powershell
$env:TOSS_CLIENT_ID = "your-client-id"
$env:TOSS_CLIENT_SECRET = "your-client-secret"
```

### 시장 데이터 조회

`TossClient`는 반드시 비동기 컨텍스트 매니저 안에서 사용합니다.

```python
import asyncio

from modules.brokers.toss import TossClient


async def main() -> None:
    async with TossClient.from_env() as client:
        prices = await client.market.prices(["005930", "AAPL"])
        candles = await client.market.candles(
            "AAPL",
            interval="1d",
            count=20,
        )
        stocks = await client.stocks.get(["005930", "AAPL"])

        print(prices)
        print(candles.candles)
        print(stocks)


asyncio.run(main())
```

### 캔들 페이지네이션

응답의 `next_before`를 다음 요청의 `before`로 전달합니다. 마지막 페이지에서는 `next_before`가 `None`입니다.

```python
async with TossClient.from_env() as client:
    first = await client.market.candles("005930", interval="1m", count=200)

    if first.next_before is not None:
        second = await client.market.candles(
            "005930",
            interval="1m",
            count=200,
            before=first.next_before,
        )
```

---

## Models

| 모델 | 역할 | 주요 필드 |
|------|------|-----------|
| `IssuedToken` | OAuth2 토큰과 만료 정보 | `access_token`, `issued_at`, `expires_at` |
| `CurrentPrice` | 종목 현재가 | `symbol`, `timestamp`, `last_price`, `currency` |
| `Candle` | 단일 OHLCV 봉 | `timestamp`, `open_price`, `high_price`, `low_price`, `close_price`, `volume` |
| `CandlePage` | 캔들 페이지 | `candles`, `next_before` |
| `StockInfo` | 종목 기본정보 | `market`, `security_type`, `status`, `shares_outstanding` |
| `KoreanMarketDetail` | 국내 시장 상세정보 | `nxt_supported`, 거래정지·정리매매 상태 |

모든 API 응답 모델은 원본 응답 객체를 `raw` 필드에 보존합니다. 가격, 거래량, 발행주식수처럼 정밀도가 중요한 숫자는 부동소수점 대신 `Decimal`로 파싱합니다.

---

## Architecture

```text
modules/brokers/toss/
├── __init__.py              공개 SDK 표면과 모델·예외 export
├── client.py                TossClient 컨텍스트와 네임스페이스 구성
├── config.py                Credentials와 기본 API URL
├── auth.py                  OAuth2 발급, 토큰 모델과 메모리 캐시
├── market.py                현재가와 캔들 고수준 API
├── stocks.py                종목 기본정보 고수준 API
├── models.py                frozen dataclass 응답 모델
├── parsers.py               JSON 응답의 타입 변환과 검증
├── exceptions.py            설정·인증·API·rate-limit 예외
├── types.py                 통화와 캔들 간격 타입
└── _internal/
    └── http.py              HTTPX 전송, 오류 envelope와 429 처리
```

이 패키지는 순수 브로커 SDK 계층입니다. `modules.adapters`, `modules.domain`, `modules.orchestration`, `modules.storage` 또는 애플리케이션 패키지를 import하지 않습니다.

---

## Error Handling

토스증권의 오류 응답은 SDK 예외로 변환됩니다.

| 예외 | 발생 조건 | 보존 정보 |
|------|-----------|-----------|
| `TossConfigError` | 자격증명 누락 또는 빈 값 | 설정 오류 메시지 |
| `TossAuthError` | 토큰 발급 실패 또는 잘못된 토큰 응답 | OAuth 오류 메시지 |
| `TossApiError` | 일반 4xx·5xx 또는 잘못된 JSON 응답 | `status_code`, `code`, `request_id`, `data` |
| `TossRateLimitError` | 재시도 후에도 HTTP 429 응답 | 일반 API 오류 정보와 `retry_after` |

```python
from modules.brokers.toss import TossApiError, TossClient


async with TossClient.from_env() as client:
    try:
        await client.market.prices("UNKNOWN")
    except TossApiError as exc:
        print(exc.status_code, exc.code, exc.request_id)
```

---

## Testing

테스트는 실제 토스증권 서버를 호출하지 않고 `httpx.MockTransport`로 토큰과 API 응답을 고정합니다.

```bash
uv run python -m pytest tests/brokers/toss/test_toss_sdk.py -q
uv run ruff check modules/brokers/toss tests/brokers/toss
uv run ruff format --check modules/brokers/toss tests/brokers/toss
```

현재 회귀 범위는 다음 동작을 포함합니다.

- OAuth2 form 요청과 토큰 캐시 재사용
- 현재가 응답의 `Decimal`·시간 타입 변환
- 캔들 요청 매개변수와 페이지네이션 응답 파싱
- 국내 종목의 시장 상세정보 파싱
- 오류 코드와 요청 ID 보존
- 비동기 컨텍스트 매니저 사용 강제
- 캔들 조회 개수 범위 검증

---

## Current Scope

현재 SDK는 인증과 읽기 전용 시장 데이터 중 현재가, 1분봉·일봉, 종목 기본정보만 지원합니다. WebSocket 실시간 API는 토스증권에서 제공하지 않으며, 계좌·보유자산·주문 API는 이 초기 SDK 범위에 포함하지 않았습니다.

FinLabs 저장소 저장, canonical domain 모델 변환, CLI 명령과 수집 워크플로는 이 패키지의 책임이 아닙니다. 필요한 경우 각각 `modules.adapters`, `modules.orchestration`, 애플리케이션 계층에서 구현해야 합니다.

---

## License

이 저장소에는 아직 별도 라이선스 파일이 없습니다.
