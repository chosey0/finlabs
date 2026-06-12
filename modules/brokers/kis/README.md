<div align="center">

# KIS SDK

**한국투자증권 Open API용 순수 파이썬 SDK — 해외주식 REST 조회와 해외·국내 실시간 WebSocket 수신**

[![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![HTTPX](https://img.shields.io/badge/HTTPX-0.27+-2F6F9F?style=for-the-badge)](https://www.python-httpx.org/)
[![WebSockets](https://img.shields.io/badge/WebSockets-13+-010101?style=for-the-badge)](https://websockets.readthedocs.io/)
[![pytest](https://img.shields.io/badge/Tested_with-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)](https://pytest.org/)

인증·엔드포인트 메타데이터·응답 정규화만 담당하는 transport 전용 SDK입니다.

[FinLabs](../../../README.md) · [Toss SDK](../toss/README.md) · [KIS CLI](../../../kis_cli/README.md)

</div>

---

## Overview

`modules.brokers.kis`는 한국투자증권(Korea Investment & Securities) Open API를 감싸는 순수 파이썬 SDK입니다. REST 조회는 **해외주식 전용**이고, WebSocket 실시간 시세는 **해외주식과 국내주식(KOSPI/KOSDAQ) 체결/호가**를 모두 지원합니다. 국내주식 REST 조회는 이 SDK 범위 밖이며, 별도 Kiwoom REST API SDK로 구현할 예정입니다.

이 패키지는 REST/WebSocket 트랜스포트, 인증, 엔드포인트 메타데이터, 응답 정규화만 담당합니다. 영속화·CLI·설정 파일 처리는 상위 `modules` 계층과 `kis_cli/`가 맡습니다.

---

## Features

| | 기능 | 설명 |
|---|------|------|
| **[인증]** | OAuth 토큰·approval key | 접근 토큰과 WebSocket approval key 발급, 동시성 안전 캐시, 만료 30초 전 선제 갱신 |
| **[시세]** | 해외주식 REST | 현재가, 기간별 OHLCV, 분봉, 거래량 급증 분석 |
| **[실시간]** | 해외 체결/호가 | `HDFSCNT0`/`HDFSASP0` — 기본 지연시세(`D`), 유료 신청 계좌는 `feed="realtime"`(`R`) |
| **[실시간]** | 국내 체결/호가 | `H0STCNT0`/`H0STASP0` — KOSPI/KOSDAQ 항상 실시간, 모의투자 지원 |
| **[안정성]** | 세션 자동 복구 | 재접속 + 자동 재구독, 서버 PINGPONG keepalive 자동 에코 |
| **[심볼]** | 해외 심볼 마스터 | 거래소별 마스터 파일 다운로드·파싱 |
| **[환경]** | real/mock 분리 | 환경별 base URL·TR ID 매핑, 모의 미지원 엔드포인트는 `MockNotSupportedError` |

지원하지 않는 범위:

- 국내주식 REST 조회
- 주문/계좌/매매 API
- 저장소, CLI 설정, 대시보드, 분석 UI

---

## Package Layout

```text
kis/
├── client.py        KisClient facade — async context manager, request(), ensure_token()
├── config.py        Credentials(from_env), 환경별 REST/WebSocket URL
├── auth/            토큰·approval key 발급/캐시 (TokenProvider, TokenCache)
├── endpoints/       EndpointSpec 레지스트리 — domestic/, overseas/
├── parsers/         REST·실시간 페이로드 → 모델 변환
├── models/          frozen dataclass 응답 모델 (raw 페이로드 보존)
├── overseas/        고수준 REST API (price / chart / analysis)
├── realtime/        WebSocket 실시간 세션 (RealtimeSession)
├── symbols.py       해외 심볼 마스터 다운로드/파싱
└── _internal/       HTTP transport, 헤더 빌더, continuation pacing
```

---

## Getting Started

### 사전 요구사항

- Python 3.12+
- `uv` (FinLabs workspace 기준)
- 한국투자증권 Open API 자격 증명 (앱키/앱시크릿)

### 자격 증명 설정

```bash
export KIS_APP_KEY="발급받은-앱키"
export KIS_APP_SECRET="발급받은-앱시크릿"
```

### REST 빠른 시작

```python
import asyncio
from modules.brokers.kis import Credentials, KisClient

async def main():
    async with KisClient(credentials=Credentials.from_env()) as client:
        price = await client.overseas.price.current("AAPL", exchange="NAS")
        print(price.symbol, price.price, price.currency)

        bars = await client.overseas.chart.daily(
            "AAPL",
            exchange="NAS",
            start="2026-01-01",
            end="2026-01-31",
        )
        print(len(bars), bars[-1].close)

        minutes = await client.overseas.chart.minute(
            "AAPL",
            exchange="NAS",
            start="2026-01-20 09:24:00",
            interval_minutes=1,
        )
        print(len(minutes))

        surge = await client.overseas.analysis.volume_surge("NAS", count=20)
        print(surge[0].symbol)

asyncio.run(main())
```

---

## Realtime Streaming

SDK만으로 CLI에서 실시간 데이터를 수신할 수 있습니다. `kis_cli` 없이 짧은 스크립트 하나면 됩니다.

### 1. 수신 스크립트

아래를 `stream.py`로 저장합니다.

```python
import asyncio

from modules.brokers.kis import KisClient, RealtimeTick


async def main() -> None:
    async with KisClient.from_env() as client:        # environment="real" 기본
        async with client.realtime.session() as ws:
            # 국내: 종목코드 6자리, 항상 실시간
            await ws.subscribe_trades("005930", market="KOSPI")
            await ws.subscribe_orderbook("005930", market="KOSPI")
            # 해외: 기본 지연시세(D). 실시간 신청 계좌면 feed="realtime"
            await ws.subscribe_trades("AAPL", market="NAS")

            async for event in ws.stream():
                if isinstance(event, RealtimeTick):
                    print(f"[체결] {event.market} {event.symbol} "
                          f"{event.price} x{event.volume} @{event.exchange_ts}")
                else:
                    best = event.asks[0]
                    print(f"[호가] {event.symbol} "
                          f"매도1 {best.ask_price}({best.ask_volume}) / "
                          f"매수1 {best.bid_price}({best.bid_volume})")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
```

### 2. 실행

```bash
uv run python stream.py
```

`Ctrl-C`로 종료합니다. 토큰/approval key 발급, 재접속 + 자동 재구독, PINGPONG 에코는 모두 세션이 알아서 처리하므로 위 코드가 전부입니다.

### 알아둘 점

| 항목 | 내용 |
|------|------|
| 장 시간 | 국내 체결은 KRX 정규장(09:00–15:30 KST)에만 흐릅니다. 해외(NAS)는 미국 장 시간 기준이고, 기본 `D` 피드는 지연시세입니다 |
| 모의투자 | `KisClient.from_env(environment="mock")`으로 전환합니다. 국내 실시간은 모의 환경을 지원하지만, 해외 실시간은 모의 미지원이라 구독 시점에 `MockNotSupportedError`가 발생합니다 |
| 구독 응답 | 등록 직후 서버의 `SUBSCRIBE SUCCESS` JSON 응답은 이벤트로 나오지 않고 내부에서 처리됩니다 |
| 디버깅 | 실패 메시지는 `modules.brokers.kis` 로거의 warning으로 나옵니다. 스크립트 상단에 `logging.basicConfig(level=logging.WARNING)`을 추가하면 보입니다 |

---

## Low-level 호출

등록된 EndpointSpec은 `lookup()`으로 조회할 수 있고, high-level facade가 아직 없는 API는 `client.request()`로 호출할 수 있습니다.

```python
from modules.brokers.kis import lookup

spec = lookup("overseas.price.current")
payload = await client.request(
    spec,
    params={"AUTH": "", "EXCD": "NAS", "SYMB": "AAPL"},
)
```

---

## 심볼 마스터

```python
from modules.brokers.kis import download_symbol_master

records = download_symbol_master("NASDAQ")
```

지원 시장은 `NASDAQ`, `NYSE`, `AMEX`, `SHANGHAI`, `SHANGHAI_INDEX`, `SHENZHEN`, `SHENZHEN_INDEX`, `TOKYO`, `HONGKONG`, `HANOI`, `HOCHIMINH`입니다.

---

## Public API Summary

```text
client.overseas.price.current()
client.overseas.chart.daily()
client.overseas.chart.minute()
client.overseas.analysis.volume_surge()
client.realtime.session().subscribe_trades()    # 해외(NAS 등) + 국내(KRX/KOSPI/KOSDAQ)
client.realtime.session().subscribe_orderbook() # 해외 + 국내
```

국내주식 REST 조회용 `client.domestic.*` 네임스페이스는 제공하지 않습니다. 국내는 실시간 WebSocket(체결/호가)만 지원합니다.

---

## Development

```bash
# SDK 단위 테스트
uv run python -m pytest tests/brokers/kis -q

# 정적 검사
uv run ruff check modules/brokers/kis
```

단위 테스트에서 실제 KIS API를 호출하지 않습니다. REST는 `httpx.MockTransport`, 실시간은 fake WebSocket으로 검증합니다.
