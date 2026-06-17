<div align="center">

# Kiwoom SDK

**키움증권 REST/WebSocket API용 순수 파이썬 SDK — OAuth, 차트, 실시간 시세**

인증, 엔드포인트 메타데이터, HTTP/WebSocket transport, 응답 정규화만
담당하는 broker SDK입니다.

[FinLabs](../../../README.md) · [KIS SDK](../kis/README.md) · [Toss SDK](../toss/README.md)

</div>

---

## Overview

`modules.brokers.kiwoom`은 키움증권 OpenAPI REST/WebSocket API를 감싸는
순수 파이썬 SDK입니다. 현재 구현 범위는 OAuth 접근토큰 발급/폐기,
국내주식 차트 조회, 실시간 주식체결/주식호가잔량 수신입니다.

이 패키지는 broker SDK 계층입니다. DuckDB/SQLite 저장, CLI, 설정 파일,
대시보드, canonical domain model 변환은 담당하지 않습니다. 그런 작업은
상위 `modules.adapters` / `modules.orchestration` / `kis_cli` 계층에서
처리합니다.

공식 문서:

- API 가이드: <https://openapi.kiwoom.com/guide/apiguide?dummyVal=0>
- 운영 도메인: `https://api.kiwoom.com`
- 모의투자 도메인: `https://mockapi.kiwoom.com`
- 개발 도메인: `https://apidev.kiwoom.com`
- 실시간 WebSocket URI: `/api/dostk/websocket`

---

## Features

| 영역 | 구현 | API ID |
|------|------|--------|
| 인증 | 접근토큰 발급 | `au10001` |
| 인증 | 접근토큰 폐기 | `au10002` |
| 차트 | 주식 틱차트 조회 | `ka10079` |
| 차트 | 주식 분봉차트 조회 | `ka10080` |
| 차트 | 주식 일봉차트 조회 | `ka10081` |
| 차트 | 주식 주봉차트 조회 | `ka10082` |
| 차트 | 주식 월봉차트 조회 | `ka10083` |
| 차트 | 주식 년봉차트 조회 | `ka10094` |
| 실시간시세 | 주식체결 | `0B` |
| 실시간시세 | 주식호가잔량 | `0D` |

지원하지 않는 범위:

- 주문, 계좌, 잔고, 조건검색
- 종목정보, 현재가, 주식시간외호가(`0E`)
- 저장소, CLI 명령, 대시보드, 분석 UI

---

## Package Layout

```text
kiwoom/
├── client.py        KiwoomClient facade — async context manager, request()
├── config.py        Credentials(from_env), 환경별 REST/WebSocket URL
├── auth/            접근토큰 발급/폐기, TokenProvider, TokenCache
├── endpoints/       EndpointSpec 레지스트리 — domestic/chart
├── parsers/         REST/WebSocket 페이로드 → SDK 모델 변환
├── models/          frozen dataclass 응답 모델(raw 페이로드 보존)
├── domestic/        국내주식 고수준 REST API(chart)
├── realtime/        국내주식 실시간 WebSocket 세션/구독
└── _internal/       HTTP transport, Kiwoom 헤더 빌더
```

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv` (FinLabs workspace 기준)
- 키움증권 REST API 앱키/시크릿키

### 자격 증명 설정

```bash
export KIWOOM_APP_KEY="발급받은-앱키"
export KIWOOM_SECRET_KEY="발급받은-시크릿키"
```

### 빠른 시작

```python
import asyncio

from modules.brokers.kiwoom import Credentials, KiwoomClient


async def main() -> None:
    async with KiwoomClient(credentials=Credentials.from_env()) as client:
        daily = await client.domestic.chart.daily(
            "005930",
            base_date="2026-06-17",
        )
        print(len(daily), daily[-1].timestamp, daily[-1].close)

        minutes = await client.domestic.chart.minute(
            "005930",
            interval_minutes=1,
            base_date="2026-06-17",
        )
        print(len(minutes), minutes[-1].timestamp, minutes[-1].close)

        ticks = await client.domestic.chart.tick("005930", tick_scope=1)
        print(len(ticks), ticks[-1].timestamp, ticks[-1].close)


asyncio.run(main())
```

`KiwoomClient`는 `async with` 안에서 사용해야 합니다. 이 범위 안에서
`httpx.AsyncClient`와 토큰 캐시 lifecycle이 관리됩니다.

---

## Chart API

```python
await client.domestic.chart.tick("005930", tick_scope=1)
await client.domestic.chart.minute("005930", interval_minutes=1, base_date="2026-06-17")
await client.domestic.chart.daily("005930", base_date="2026-06-17")
await client.domestic.chart.weekly("005930", base_date="2026-06-17")
await client.domestic.chart.monthly("005930", base_date="2026-06-17")
await client.domestic.chart.yearly("005930", base_date="2026-06-17")
```

지원 범위:

- `tick_scope`: `1`, `3`, `5`, `10`, `30`
- `interval_minutes`: `1`, `3`, `5`, `10`, `15`, `30`, `45`, `60`
- `adjusted=True`: `upd_stkpc_tp=1`
- `max_pages=None`: 기본값. 응답 헤더 `cont-yn=Y`, `next-key`가 끝날 때까지 전체 페이지 조회
- `max_pages=5`: 필요한 경우 연속조회 페이지 수를 명시적으로 제한

반환 모델은 `ChartBar`입니다.

```python
ChartBar(
    market="KRX",
    symbol="005930",
    interval="1d",
    timestamp="2026-06-17",
    open=...,
    high=...,
    low=...,
    close=...,
    volume=...,
    raw={...},
)
```

키움 차트 응답은 일부 가격 필드에 등락 방향을 부호로 붙입니다. SDK는
OHLC 가격에는 절댓값을 사용하고, 전일대비 값인 `change`에는 부호를
보존합니다.

---

## Realtime API

```python
import asyncio

from modules.brokers.kiwoom import KiwoomClient


async def main() -> None:
    async with KiwoomClient.from_env() as client:
        async with client.realtime.session() as ws:
            await ws.subscribe_trades("005930")
            await ws.subscribe_orderbook("005930")

            async for event in ws.stream():
                print(event)


asyncio.run(main())
```

지원 채널:

| 메서드 | API ID | 반환 모델 |
|--------|--------|-----------|
| `subscribe_trades("005930")` | `0B` | `RealtimeTick` |
| `subscribe_orderbook("005930")` | `0D` | `OrderBookSnapshot` |

WebSocket 로그인은 REST 접근토큰으로 수행합니다. 서버가 `PING` 프레임을
보내면 SDK가 동일 payload를 즉시 echo합니다. 실시간 이벤트 모델은
거래소 시각(`exchange_ts`), 수신 시각(`received_at`), 수신 순번
(`received_seq`)과 원문 `values`를 함께 보존합니다.

---

## Authentication

동기/비동기 토큰 발급 함수를 모두 제공합니다.

```python
from modules.brokers.kiwoom import issue_access_token

issued = issue_access_token(
    environment="real",
    app_key="...",
    secret_key="...",
)
print(issued.expires_at)
```

고수준 사용에서는 직접 호출할 필요가 없습니다. `KiwoomClient`가 필요한
시점에 토큰을 발급하고 `TokenCache`에 저장합니다.

토큰 폐기:

```python
from modules.brokers.kiwoom import revoke_access_token

revoke_access_token(
    environment="real",
    app_key="...",
    secret_key="...",
    token="...",
)
```

---

## Low-level 호출

등록된 `EndpointSpec`은 `lookup()`으로 조회할 수 있습니다.

```python
from modules.brokers.kiwoom import lookup

spec = lookup("domestic.chart.daily")
payload = await client.request(
    spec,
    json_body={
        "stk_cd": "005930",
        "base_dt": "20260617",
        "upd_stkpc_tp": "1",
    },
)
```

연속조회 헤더가 필요하면 `request_raw()`를 사용합니다.

```python
response = await client.request_raw(spec, json_body=body)
print(response.headers.get("cont-yn"), response.headers.get("next-key"))
```

---

## Development

```bash
# 정적 검사
uv run ruff check modules/brokers/kiwoom

# 컴파일 확인
PYTHONPYCACHEPREFIX=/tmp/finlabs-pycache \
  uv run python -m compileall -q modules/brokers/kiwoom

# 아키텍처 boundary 테스트
uv run python -m pytest tests/architecture/test_boundaries.py -q
```

단위 테스트나 예제에서는 실제 키움 API를 호출하지 말고 `httpx.MockTransport`
로 응답을 주입합니다.
