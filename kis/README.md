# kis

한국투자증권(Korea Investment & Securities) Open API를 다루는 순수 파이썬 SDK입니다.
REST/WebSocket 트랜스포트, 인증, 응답 정규화만 담당하며, 영속화·CLI·설정 파일 같은
애플리케이션 레이어 책임은 포함하지 않습니다(그건 같은 저장소의 `kis_cli` 패키지가 맡습니다).

> **Stage:** 5 완료. 국내/해외 현재가·차트 high-level facade, WebSocket
> 실시간 체결/호가 스트리밍, 종목정보·순위분석·시세분석·업종/기타
> EndpointSpec 등록과 주요 분석 facade를 사용할 수 있습니다. 자세한 상태는
> [로드맵](#로드맵)을 참고하세요.

---

## 왜 이 SDK인가

- **데이터 주도 엔드포인트.** URL, TR ID, 모의투자 지원 여부, 필수 파라미터를
  `EndpointSpec` dataclass에 담아 한곳에서 조회합니다. KIS Open API 사양이 바뀌면
  엔드포인트 모듈 한 줄만 고치면 됩니다.
- **트랜스포트와 파싱 분리.** `kis.parsers.rest.parse_*`는 모두 raw `dict`를 받아
  도메인 모델을 반환하는 순수 함수라, 네트워크 없이 단위 테스트가 가능합니다.
- **모의투자 미지원 가드.** `tr_id_mock=None`으로 등록된 엔드포인트는
  `spec.tr_id_for("mock")` 호출 시 `MockNotSupportedError`를 던집니다. 따라서
  `client.overseas.chart.daily(...)`처럼 high-level 메서드에서도 자동으로 차단됩니다.
- **Async-first, sync wrapper.** REST 데이터 호출은 httpx async가 기본이며, OAuth
  토큰 발급은 sync/async 둘 다 제공합니다.
- **외부 의존성 최소화.** runtime은 `httpx`, `websockets` 두 개만 필요합니다.
  모델은 `@dataclass(frozen=True)`로 표준 라이브러리만 사용합니다.

---

## 설치

이 패키지는 별도 PyPI 배포 전이며, 현재는 `kis-cli` 저장소의 일부로 함께 빌드됩니다.

```bash
uv sync
# 또는
pip install -e .
```

런타임 의존성: `httpx>=0.27.0`, `websockets>=13.0`.

---

## 빠른 시작

### 1) 한 줄 호출 (high-level facade)

```python
import asyncio
from kis import Credentials, KisClient, RealtimeTick

async def main():
    async with KisClient(credentials=Credentials.from_env()) as client:
        # 국내 현재가
        samsung = await client.domestic.price.current("005930", market="KOSPI")
        print(samsung.name, samsung.price)         # '삼성전자' Decimal('70500')

        # 해외 현재가
        apple = await client.overseas.price.current("AAPL", exchange="NAS")
        print(apple.name, apple.price, apple.currency)

        # 국내 일봉 (페이지네이션 자동)
        bars = await client.domestic.chart.daily(
            "005930", start="2026-01-01", end="2026-01-31",
        )
        print(len(bars), bars[-1].close)

        # 해외 분봉
        minutes = await client.overseas.chart.minute(
            "AAPL", exchange="NAS", start="2026-01-20 09:24:00", interval_minutes=1,
        )

        # 종목정보/순위/분석
        product = await client.domestic.symbols.product_info("005930")
        financials = await client.domestic.symbols.financial_summary("005930")
        volume_rank = await client.domestic.rank.volume("J", count=20)
        investor_flow = await client.domestic.analysis.investor_flow(
            "005930", start="2026-01-01", end="2026-01-31",
        )
        overseas_surge = await client.overseas.analysis.volume_surge("NAS", count=20)

        # 국내 실시간 체결
        async with client.realtime.session() as ws:
            await ws.subscribe_trades("005930", market="KRX")
            async for event in ws.stream():
                if isinstance(event, RealtimeTick):
                    print(event.symbol, event.price, event.exchange_ts)
                    break

asyncio.run(main())
```

핵심 규약 세 가지:

1. **`KisClient`는 반드시 `async with`로 진입.** httpx의 AsyncClient 수명을
   안전하게 관리하고, 컨텍스트 종료 시 connection을 정리합니다.
2. **토큰은 자동 발급/캐시.** 첫 호출 시 `/oauth2/tokenP`로 토큰을 발급하고
   `TokenCache`(기본 `MemoryTokenCache`)에 저장합니다. 같은 컨텍스트 안에서
   여러 번 호출해도 토큰 발급은 한 번만 일어납니다.
3. **모의는 엔드포인트별로 검증.** `environment="mock"`으로 만든 클라이언트는
   `tr_id_mock=None` 엔드포인트(해외 시세 등)를 호출하는 즉시
   `MockNotSupportedError`를 던집니다.

### 1-1) WebSocket 실시간 스트리밍

```python
import asyncio
from kis import Credentials, KisClient, RealtimeTick

async def main():
    async with KisClient(credentials=Credentials.from_env()) as client:
        async with client.realtime.session() as ws:
            await ws.subscribe_trades("005930", market="KRX")
            async for event in ws.stream():
                if isinstance(event, RealtimeTick):
                    print(event.symbol, event.price, event.exchange_ts)
                    break

asyncio.run(main())
```

`client.realtime.session()`은 `/oauth2/Approval`로 WebSocket 접속키를 발급해
메모리 토큰 캐시에 저장하고, `subscribe_trades`/`subscribe_orderbook` 호출 시
KIS WebSocket 등록 프레임을 전송합니다. 국내 KRX 체결/호가는 모의 TR ID가 있고,
해외 체결/호가는 KIS 문서상 모의투자 미지원입니다.

### 2) `Credentials`

```python
from kis import Credentials

# 환경변수 KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT, KIS_ACCOUNT_PRODUCT 사용
credentials = Credentials.from_env()

# 또는 직접 주입
credentials = Credentials(app_key="...", app_secret="...")
```

`Credentials`는 frozen dataclass라서 객체가 만들어진 뒤 키/시크릿이 바뀌지 않습니다.

### 3) 토큰 캐시 교체

기본 `MemoryTokenCache`는 프로세스 메모리에만 토큰을 보관합니다. 파일/Redis 등에
저장하고 싶으면 `TokenCache` Protocol을 구현하세요.

```python
from kis import TokenCache, TokenRecord, KisClient, Credentials

class FileTokenCache:
    def __init__(self, path):
        self._path = path
    def get(self, key: str) -> TokenRecord | None: ...
    def set(self, key: str, record: TokenRecord) -> None: ...
    def delete(self, key: str) -> None: ...

async with KisClient(
    credentials=Credentials.from_env(),
    token_cache=FileTokenCache("/var/run/kis/token.json"),
) as client:
    ...
```

캐시 키는 `f"{environment}:{app_key}"` 규칙으로 자동 생성됩니다. profile 같은
cli 개념은 SDK에 끌어들이지 않습니다.

### 4) 토큰을 직접 발급하고 싶다면

CI 스크립트처럼 한 번만 토큰을 받고 끝낼 때는 `KisClient`를 거치지 않아도 됩니다.

```python
from kis.auth.oauth import issue_access_token

token = issue_access_token(
    environment="real",
    app_key="...",
    app_secret="...",
)
token.access_token        # 'eyJ...'
token.expires_at          # tz-aware datetime
```

비동기 컨텍스트에서는 `issue_access_token_async`를 사용하세요.

### 5) low-level: EndpointSpec lookup + parser 직접 호출

high-level 메서드로 표현되지 않는 새 KIS 엔드포인트를 시험하고 싶다면 SDK의
구성 부품에 직접 접근할 수 있습니다.

```python
from kis import lookup
from kis.parsers.rest import parse_domestic_current_price, output_dict

async with KisClient(credentials=...) as client:
    spec = lookup("domestic.price.current")
    payload = await client.request(
        spec,
        params={"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"},
    )
    price = parse_domestic_current_price(
        market="KOSPI", symbol="005930", output=output_dict(payload),
    )
```

`client.request(spec, ...)`는 high-level 메서드들이 내부적으로 거치는 같은
경로입니다 — 토큰 자동 발급, 헤더 조립, `rt_cd` 검증이 한 번에 처리됩니다.

### 6) 심볼 마스터 다운로드

```python
from kis import download_symbol_master

records = download_symbol_master("KOSPI")     # list[SymbolRecord]
records[0].symbol, records[0].korean_name
# ('005930', '삼성전자')
```

심볼 마스터는 KIS의 공개 정적 zip(인증 불필요)을 받아 cp949로 디코딩하므로
`KisClient`나 토큰이 필요 없습니다.

---

## 아키텍처 한눈에 보기

```text
kis/
├── client.py                # KisClient (facade) — async context + 토큰 자동 발급
├── config.py                # Credentials, rest_base_url, websocket_url
├── types.py                 # Environment, Market, Interval 등 Literal
├── exceptions.py            # KisError 계층
├── symbols.py               # 심볼 마스터 다운로드/파싱/상수
│
├── auth/
│   ├── oauth.py             # IssuedToken, issue_access_token(_async), mask_sensitive_message
│   └── cache.py             # TokenCache Protocol + MemoryTokenCache
│
├── endpoints/
│   ├── registry.py          # EndpointSpec + register/lookup/names
│   ├── domestic/basic_quote.py
│   └── overseas/basic_quote.py
│
├── models/                  # CurrentPrice, OhlcvBar, RealtimeTick, OrderBookSnapshot 등
├── parsers/                 # rest.py, realtime.py
│
├── _internal/               # HTTP/WS 트랜스포트 (외부 사용 금지)
│   ├── http.py              # AsyncHttpTransport
│   └── headers.py           # build_rest_headers, WS subscribe builder
│
├── domestic/
│   ├── price.py             # DomesticPriceAPI (.current)
│   ├── chart.py             # DomesticChartAPI (.daily/.weekly/.monthly/.yearly)
│   ├── symbols.py           # DomesticSymbolsAPI (.product_info/.financial_summary)
│   ├── rank.py              # DomesticRankAPI (.volume)
│   └── analysis.py          # DomesticAnalysisAPI (.investor_flow)
├── overseas/
│   ├── price.py             # OverseasPriceAPI (.current)
│   ├── chart.py             # OverseasChartAPI (.daily/.minute)
│   └── analysis.py          # OverseasAnalysisAPI (.volume_surge)
└── realtime/                # RealtimeSession (체결/호가 subscribe + async stream)
```

밑줄로 시작하는 `_internal/`은 SDK 외부에서 import하지 않는 것이 약속입니다.
파이썬은 강제하지 않지만, 이 경계가 바뀔 일이 잦은 부분과 안정적인 부분을
가릅니다.

---

## 디자인 원칙

1. **순수성.** SDK는 파일 시스템, DB, KST 포맷 같은 호스트 환경에 의존하지 않습니다.
   `download_symbol_master`가 `downloaded_at`을 인자로 받는 것도 그래서입니다.
2. **트랜스포트와 파싱은 다른 책임.** 파서는 raw dict만 받고, HTTP는 응답을 dict로
   환원합니다. 한쪽을 모킹해도 다른 쪽이 영향받지 않습니다.
3. **데이터 주도 메타데이터.** path/tr_id/필수 파라미터/모의 지원 여부를 `EndpointSpec`
   하나에 모아 등록합니다. KIS 문서가 단일 진실 공급원이고, 코드는 그 사본입니다.
4. **frozen dataclass 모델.** Pydantic을 도입하지 않아 런타임 오버헤드와 의존성이
   적습니다. 직렬화는 `dataclasses.asdict`로 충분합니다.
5. **명시적 환경.** `Environment = Literal["real", "mock"]`. real/mock 분기를
   `tr_id_for(env)`에서 한곳에서만 합니다.
6. **`async with`로 lifecycle 명시.** `KisClient`의 httpx connection·토큰 캐시는
   컨텍스트 진입 시 활성화되고 종료 시 정리됩니다. lifecycle을 사용자에게 숨기지
   않습니다.

---

## 등록된 엔드포인트 (현재)

| 이름 | 메서드 | TR ID (real) | 모의 | high-level |
| --- | --- | --- | --- | --- |
| `domestic.analysis.capture_uplowprice` | GET | FHKST130000C0 | 미지원 | `(low-level만)` |
| `domestic.analysis.comp_program_trade_daily` | GET | FHPPG04600001 | 미지원 | `(low-level만)` |
| `domestic.analysis.comp_program_trade_today` | GET | FHPPG04600101 | 미지원 | `(low-level만)` |
| `domestic.analysis.daily_credit_balance` | GET | FHPST04760000 | 미지원 | `(low-level만)` |
| `domestic.analysis.daily_loan_trans` | GET | HHPST074500C0 | 미지원 | `(low-level만)` |
| `domestic.analysis.daily_short_sale` | GET | FHPST04830000 | 미지원 | `(low-level만)` |
| `domestic.analysis.exp_price_trend` | GET | FHPST01810000 | 미지원 | `(low-level만)` |
| `domestic.analysis.foreign_institution_total` | GET | FHPTJ04400000 | 미지원 | `(low-level만)` |
| `domestic.analysis.frgnmem_pchs_trend` | GET | FHKST644400C0 | 미지원 | `(low-level만)` |
| `domestic.analysis.frgnmem_trade_estimate` | GET | FHKST644100C0 | 미지원 | `(low-level만)` |
| `domestic.analysis.frgnmem_trade_trend` | GET | FHPST04320000 | 미지원 | `(low-level만)` |
| `domestic.analysis.inquire_daily_trade_volume` | GET | FHKST03010800 | 미지원 | `(low-level만)` |
| `domestic.analysis.inquire_investor_daily_by_market` | GET | FHPTJ04040000 | 미지원 | `(low-level만)` |
| `domestic.analysis.inquire_investor_time_by_market` | GET | FHPTJ04030000 | 미지원 | `(low-level만)` |
| `domestic.analysis.inquire_member_daily` | GET | FHPST04540000 | 미지원 | `(low-level만)` |
| `domestic.analysis.intstock_grouplist` | GET | HHKCM113004C7 | 미지원 | `(low-level만)` |
| `domestic.analysis.intstock_multprice` | GET | FHKST11300006 | 미지원 | `(low-level만)` |
| `domestic.analysis.intstock_stocklist_by_group` | GET | HHKCM113004C6 | 미지원 | `(low-level만)` |
| `domestic.analysis.investor_program_trade_today` | GET | HHPPG046600C1 | 미지원 | `(low-level만)` |
| `domestic.analysis.investor_trade_by_stock_daily` | GET | FHPTJ04160001 | 미지원 | `client.domestic.analysis.investor_flow` |
| `domestic.analysis.investor_trend_estimate` | GET | HHPTJ04160200 | 미지원 | `(low-level만)` |
| `domestic.analysis.mktfunds` | GET | FHKST649100C0 | 미지원 | `(low-level만)` |
| `domestic.analysis.overtime_exp_trans_fluct` | GET | FHKST11860000 | 미지원 | `(low-level만)` |
| `domestic.analysis.pbar_tratio` | GET | FHPST01130000 | 미지원 | `(low-level만)` |
| `domestic.analysis.program_trade_by_stock` | GET | FHPPG04650101 | 미지원 | `(low-level만)` |
| `domestic.analysis.program_trade_by_stock_daily` | GET | FHPPG04650201 | 미지원 | `(low-level만)` |
| `domestic.analysis.psearch_result` | GET | HHKST03900400 | 미지원 | `(low-level만)` |
| `domestic.analysis.psearch_title` | GET | HHKST03900300 | 미지원 | `(low-level만)` |
| `domestic.analysis.tradprt_byamt` | GET | FHKST111900C0 | 미지원 | `(low-level만)` |
| `domestic.chart.ohlcv` | GET | FHKST03010100 | 지원 | `client.domestic.chart.daily/.weekly/.monthly/.yearly` |
| `domestic.price.current` | GET | FHKST01010100 | 지원 | `client.domestic.price.current` |
| `domestic.rank.after_hour_balance` | GET | FHPST01760000 | 미지원 | `(low-level만)` |
| `domestic.rank.bulk_trans_num` | GET | FHKST190900C0 | 미지원 | `(low-level만)` |
| `domestic.rank.credit_balance` | GET | FHKST17010000 | 미지원 | `(low-level만)` |
| `domestic.rank.disparity` | GET | FHPST01780000 | 미지원 | `(low-level만)` |
| `domestic.rank.dividend_rate` | GET | HHKDB13470100 | 미지원 | `(low-level만)` |
| `domestic.rank.exp_trans_updown` | GET | FHPST01820000 | 미지원 | `(low-level만)` |
| `domestic.rank.finance_ratio` | GET | FHPST01750000 | 미지원 | `(low-level만)` |
| `domestic.rank.fluctuation` | GET | FHPST01700000 | 미지원 | `(low-level만)` |
| `domestic.rank.hts_top_view` | GET | HHMCM000100C0 | 미지원 | `(low-level만)` |
| `domestic.rank.market_cap` | GET | FHPST01740000 | 미지원 | `(low-level만)` |
| `domestic.rank.market_value` | GET | FHPST01790000 | 미지원 | `(low-level만)` |
| `domestic.rank.near_new_highlow` | GET | FHPST01870000 | 미지원 | `(low-level만)` |
| `domestic.rank.overtime_fluctuation` | GET | FHPST02340000 | 미지원 | `(low-level만)` |
| `domestic.rank.overtime_volume` | GET | FHPST02350000 | 미지원 | `(low-level만)` |
| `domestic.rank.prefer_disparate_ratio` | GET | FHPST01770000 | 미지원 | `(low-level만)` |
| `domestic.rank.profit_asset_index` | GET | FHPST01730000 | 미지원 | `(low-level만)` |
| `domestic.rank.quote_balance` | GET | FHPST01720000 | 미지원 | `(low-level만)` |
| `domestic.rank.short_sale` | GET | FHPST04820000 | 미지원 | `(low-level만)` |
| `domestic.rank.top_interest_stock` | GET | FHPST01800000 | 미지원 | `(low-level만)` |
| `domestic.rank.traded_by_company` | GET | FHPST01860000 | 미지원 | `(low-level만)` |
| `domestic.rank.volume` | GET | FHPST01710000 | 미지원 | `client.domestic.rank.volume` |
| `domestic.rank.volume_power` | GET | FHPST01680000 | 미지원 | `(low-level만)` |
| `domestic.realtime.orderbook` | WEBSOCKET | H0STASP0 | 지원 | `client.realtime.session().subscribe_orderbook(..., market="KRX")` |
| `domestic.realtime.trades` | WEBSOCKET | H0STCNT0 | 지원 | `client.realtime.session().subscribe_trades(..., market="KRX")` |
| `domestic.sector.chk_holiday` | GET | CTCA0903R | 미지원 | `(low-level만)` |
| `domestic.sector.comp_interest` | GET | FHPST07020000 | 미지원 | `(low-level만)` |
| `domestic.sector.exp_index_trend` | GET | FHPST01840000 | 미지원 | `(low-level만)` |
| `domestic.sector.exp_total_index` | GET | FHKUP11750000 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_daily_indexchartprice` | GET | FHKUP03500100 | 지원 | `(low-level만)` |
| `domestic.sector.inquire_index_category_price` | GET | FHPUP02140000 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_index_daily_price` | GET | FHPUP02120000 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_index_price` | GET | FHPUP02100000 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_index_tickprice` | GET | FHPUP02110100 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_index_timeprice` | GET | FHPUP02110200 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_time_indexchartprice` | GET | FHKUP03500200 | 미지원 | `(low-level만)` |
| `domestic.sector.inquire_vi_status` | GET | FHPST01390000 | 미지원 | `(low-level만)` |
| `domestic.sector.market_time` | GET | HHMCM000002C0 | 미지원 | `(low-level만)` |
| `domestic.sector.news_title` | GET | FHKST01011800 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.balance_sheet` | GET | FHKST66430100 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.bonus_issue` | GET | HHKDB669101C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.cap_dcrs` | GET | HHKDB669106C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.credit_by_company` | GET | FHPST04770000 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.dividend` | GET | HHKDB669102C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.estimate_perform` | GET | HHKST668300C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.financial_ratio` | GET | FHKST66430300 | 미지원 | `client.domestic.symbols.financial_summary` |
| `domestic.symbol_info.forfeit` | GET | HHKDB669109C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.growth_ratio` | GET | FHKST66430800 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.income_statement` | GET | FHKST66430200 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.invest_opbysec` | GET | FHKST663400C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.invest_opinion` | GET | FHKST663300C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.lendable_by_company` | GET | CTSC2702R | 미지원 | `(low-level만)` |
| `domestic.symbol_info.list_info` | GET | HHKDB669107C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.mand_deposit` | GET | HHKDB669110C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.merger_split` | GET | HHKDB669104C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.other_major_ratios` | GET | FHKST66430500 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.paidin_capin` | GET | HHKDB669100C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.product_info` | GET | CTPF1604R | 미지원 | `client.domestic.symbols.product_info` |
| `domestic.symbol_info.profit_ratio` | GET | FHKST66430400 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.pub_offer` | GET | HHKDB669108C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.purreq` | GET | HHKDB669103C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.rev_split` | GET | HHKDB669105C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.sharehld_meet` | GET | HHKDB669111C0 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.stability_ratio` | GET | FHKST66430600 | 미지원 | `(low-level만)` |
| `domestic.symbol_info.stock_info` | GET | CTPF1002R | 미지원 | `(low-level만)` |
| `overseas.analysis.brknews_title` | GET | FHKST01011801 | 미지원 | `(low-level만)` |
| `overseas.analysis.colable_by_company` | GET | CTLN4050R | 미지원 | `(low-level만)` |
| `overseas.analysis.market_cap` | GET | HHDFS76350100 | 미지원 | `(low-level만)` |
| `overseas.analysis.new_highlow` | GET | HHDFS76300000 | 미지원 | `(low-level만)` |
| `overseas.analysis.news_title` | GET | HHPSTH60100C1 | 미지원 | `(low-level만)` |
| `overseas.analysis.period_rights` | GET | CTRGT011R | 미지원 | `(low-level만)` |
| `overseas.analysis.price_fluct` | GET | HHDFS76260000 | 미지원 | `(low-level만)` |
| `overseas.analysis.rights_by_ice` | GET | HHDFS78330900 | 미지원 | `(low-level만)` |
| `overseas.analysis.trade_growth` | GET | HHDFS76330000 | 미지원 | `(low-level만)` |
| `overseas.analysis.trade_pbmn` | GET | HHDFS76320010 | 미지원 | `(low-level만)` |
| `overseas.analysis.trade_turnover` | GET | HHDFS76340000 | 미지원 | `(low-level만)` |
| `overseas.analysis.trade_vol` | GET | HHDFS76310010 | 미지원 | `(low-level만)` |
| `overseas.analysis.updown_rate` | GET | HHDFS76290000 | 미지원 | `(low-level만)` |
| `overseas.analysis.volume_power` | GET | HHDFS76280000 | 미지원 | `(low-level만)` |
| `overseas.analysis.volume_surge` | GET | HHDFS76270000 | 미지원 | `client.overseas.analysis.volume_surge` |
| `overseas.chart.dailyprice` | GET | HHDFS76240000 | 미지원 | `client.overseas.chart.daily` |
| `overseas.chart.minute` | GET | HHDFS76950200 | 미지원 | `client.overseas.chart.minute` |
| `overseas.chart.ohlcv` | GET | FHKST03030100 | 미지원 | `(low-level만)` |
| `overseas.price.current` | GET | HHDFS00000300 | 미지원 | `client.overseas.price.current` |
| `overseas.realtime.orderbook` | WEBSOCKET | HDFSASP0 | 미지원 | `client.realtime.session().subscribe_orderbook(..., exchange="NAS")` |
| `overseas.realtime.trades` | WEBSOCKET | HDFSCNT0 | 미지원 | `client.realtime.session().subscribe_trades(..., exchange="NAS")` |

`kis.names()`로 런타임에 등록된 전체 목록을 확인할 수 있습니다.


---

## 예외 계층

```text
KisError                       # 모든 SDK 예외의 부모
├── KisConfigError             # 자격증명·환경 설정 문제
├── KisAuthError               # 토큰 발급/만료 관련
├── KisApiError                # KIS REST 응답이 rt_cd != "0" 이거나 HTTP 4xx/5xx
├── MockNotSupportedError      # mock 환경에서 미지원 엔드포인트 호출
└── KisRealtimeError           # WebSocket 연결/구독/프레임 파싱 실패
```

`KisApiError`는 KIS가 돌려주는 `status_code`, `rt_cd`, `msg_cd`, `msg1`을 그대로
보존해, 호출자가 에러 종류를 코드로 분기할 수 있게 합니다.

---

## 보안 주의사항

- `mask_sensitive_message`는 `appkey/appsecret/access_token` 같은 KIS 시크릿이
  로그·예외 메시지에 새는 것을 막습니다. 사용자 환경의 로깅 파이프라인이 응답
  본문을 그대로 찍는다면 마스킹을 한 번 더 적용해주세요.
- `TokenCache`의 기본 구현은 `MemoryTokenCache`(프로세스 메모리)입니다. 파일에
  저장한다면 권한(예: `0600`)을 직접 관리해야 합니다.
- 자격증명은 코드/리포지토리에 박지 말고 환경변수 또는 OS 키체인을 사용하세요.

---

## 로드맵

| Stage | 상태 | 내용 |
| --- | --- | --- |
| 1 | ✅ | 패키지 골격(`KisClient`, `EndpointSpec`, 예외, 트랜스포트 스켈레톤) |
| 2 | ✅ | 기존 `kis_cli/core`의 auth·price·chart·symbol_master를 SDK로 이전, parser 정규화 |
| 3 | ✅ | high-level facade: `domestic.price.current`, `domestic.chart.daily/.weekly/.monthly/.yearly`, `overseas.price.current`, `overseas.chart.daily/.minute`. 토큰 자동 발급/캐시 |
| 4 | ✅ | WebSocket `RealtimeSession`: approval key 발급/캐시, 체결·호가 subscribe/unsubscribe, async generator 스트리밍 |
| 5 | ✅ | 나머지 워크북 등록: 종목정보, 순위분석, 시세분석, 업종/기타 + 주요 facade 5개 |
| 6 | ⏳ | sync wrapper 정식화, PyPI 분리 배포 |

각 stage는 `.agents/kis-skill/resources/` 안의 KIS Excel API 문서를 단일 진실
공급원으로 삼습니다.

---

## 라이선스

저장소 루트의 `LICENSE`를 따릅니다(현재 미정). 외부 배포 전까지는 내부 사용만
허용됩니다.
