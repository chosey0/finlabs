# modules.brokers.kis

한국투자증권(Korea Investment & Securities) Open API용 순수 파이썬 SDK입니다.
현재 FinLabs에서 KIS SDK는 **해외주식 데이터 조회 전용**으로 유지합니다. 국내주식 데이터 조회는 이 SDK에서 제거했으며, 별도 Kiwoom REST API SDK로 구현할 예정입니다.

이 패키지는 REST/WebSocket 트랜스포트, 인증, 엔드포인트 메타데이터, 응답 정규화만 담당합니다. 영속화·CLI·설정 파일 처리는 상위 `modules` 계층과 `kis_cli/`가 맡습니다.

## 지원 범위

- OAuth access token 발급/캐시
- WebSocket approval key 발급/캐시
- 해외주식 현재가
- 해외주식 기간별 OHLCV
- 해외주식 분봉
- 해외주식 거래량 급증 분석
- 해외주식 실시간 체결/호가 WebSocket
- 해외 심볼 마스터 다운로드/파싱

지원하지 않는 범위:

- 국내주식 REST/WebSocket 조회
- 주문/계좌/매매 API
- 저장소, CLI 설정, 대시보드, 분석 UI

## 빠른 시작

```python
import asyncio
from modules.brokers.kis import Credentials, KisClient, RealtimeTick

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

        async with client.realtime.session() as ws:
            await ws.subscribe_trades("AAPL", market="NAS")
            async for event in ws.stream():
                if isinstance(event, RealtimeTick):
                    print(event.symbol, event.price, event.exchange_ts)
                    break

asyncio.run(main())
```

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

## 심볼 마스터

```python
from modules.brokers.kis import download_symbol_master

records = download_symbol_master("NASDAQ")
```

지원 시장은 `NASDAQ`, `NYSE`, `AMEX`, `SHANGHAI`, `SHANGHAI_INDEX`, `SHENZHEN`, `SHENZHEN_INDEX`, `TOKYO`, `HONGKONG`, `HANOI`, `HOCHIMINH`입니다.

## 공개 API 요약

```text
client.overseas.price.current()
client.overseas.chart.daily()
client.overseas.chart.minute()
client.overseas.analysis.volume_surge()
client.realtime.session().subscribe_trades()
client.realtime.session().subscribe_orderbook()
```

국내주식 관련 `client.domestic.*`, 국내 parser, 국내 endpoint registry는 제공하지 않습니다.
