<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# domestic (endpoints)

## Purpose
국내(KRX/NXT) KIS Open API의 **EndpointSpec 등록 모듈** 모음입니다. 각 파일은 KIS가 배포한 엑셀 워크북(`.agents/kis-skill/resources/[국내주식] *.xlsx`) 한 권에 대응하며, import 시점에 `kis.endpoints.registry.register()`를 호출해 글로벌 레지스트리에 spec을 추가합니다. 비즈니스 로직 없음 — 순수 메타데이터입니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | 모든 서브모듈(`analysis`, `basic_quote`, `rank`, `realtime`, `sector`, `symbol_info`)을 import해 spec 등록을 트리거 |
| `basic_quote.py` | `[국내주식] 기본시세.xlsx` — `domestic.price.current` (FHKST01010100, mock OK), `domestic.chart.ohlcv` (FHKST03010100, mock OK, `supports_tr_cont=True`) |
| `analysis.py` | `[국내주식] 시세분석.xlsx` — `domestic.analysis.psearch_title/result`, `intstock_grouplist/multprice`, `investor_trade_by_stock_daily` 등 (대량 spec, `_SPECS` 튜플 + 루프 등록) |
| `rank.py` | `[국내주식] 순위분석.xlsx` — `domestic.rank.volume` (FHPST01710000), `fluctuation`, `quote_balance` 등 거래량/등락률/호가 순위 |
| `sector.py` | `[국내주식] 업종_기타.xlsx` — `domestic.sector.inquire_index_price/daily_price/tickprice/timeprice/time_indexchartprice` 등 업종 지수 시세 |
| `symbol_info.py` | `[국내주식] 종목정보.xlsx` — `domestic.symbol_info.product_info` (CTPF1604R), `stock_info` (CTPF1002R), `balance_sheet`/`income_statement`/`financial_ratio`/`profit_ratio` 등 재무제표 |
| `realtime.py` | `[국내주식] 실시간시세.xlsx` — `domestic.realtime.trades` (H0STCNT0, WebSocket), `domestic.realtime.orderbook` (H0STASP0) |

## For AI Agents

### Working In This Directory
- **모든 spec은 `register()`로 등록**하고 모듈 import 시점에 실행되어야 합니다. `endpoints/__init__.py`가 import 트리거 역할을 하므로 새 파일을 추가하면 `__init__.py`의 import 라인에도 포함시키세요.
- 등록 패턴은 두 가지:
  - **단일/소수 spec**: 모듈 변수로 노출 (`CURRENT_PRICE = register(EndpointSpec(...))`) — `basic_quote.py`, `realtime.py`처럼 다른 모듈에서 직접 참조할 만한 핵심 endpoint.
  - **대량 spec**: `_SPECS = ((name, path, tr_id_real, tr_id_mock, required_params, korean_label), ...)` 튜플 + 모듈 끝에서 루프로 `register()` — `analysis.py`, `rank.py`, `sector.py`, `symbol_info.py` 패턴.
- `name`은 반드시 `domestic.<group>.<action>` 형식으로 통일합니다.
- 국내 endpoint는 대부분 mock TR ID가 real과 동일하지만, KIS 명세를 확인 후 다르면 정확히 입력합니다. mock 미지원이면 `None`.
- 마지막 필드(한국어 API 명)는 원본 엑셀 워크북의 "API 명" 컬럼에서 그대로 복사해 추적성을 유지합니다.
- WebSocket realtime endpoint는 `method="POST"`, `required_headers=("approval_key", "custtype", "tr_type", "content-type")`, `required_params=("tr_id", "tr_key")` 패턴을 따릅니다.

### Testing Requirements
- 새 endpoint 등록 후 `tests/test_kis_package.py`에 `lookup("domestic.<...>")` 호출이 성공하는지 회귀 케이스 추가.
- 중복 이름 등록 시 `KisConfigError`가 발생하는지 회귀 한 줄 확인.

### Common Patterns
- 모듈 docstring 첫 줄에 원본 엑셀 파일명을 명시합니다 (`"""EndpointSpec registry for `[국내주식] 기본시세.xlsx`."""`) — 어느 워크북에서 왔는지 추적용.
- `supports_tr_cont=True`는 KIS 응답 헤더 `tr_cont`로 페이지네이션이 가능한 endpoint에만 표시.
- `required_params` 순서는 KIS 문서 그대로 — 사전순 정렬 등은 하지 마세요.

## Dependencies

### Internal
- `kis.endpoints.registry` — `EndpointSpec`, `register`

### External
- 없음.

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
