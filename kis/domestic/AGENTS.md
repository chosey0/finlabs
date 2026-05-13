<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-13 -->

# domestic

## Purpose
국내(KRX/NXT) REST API의 **고수준 클라이언트**입니다. `KisClient.domestic.price.current("005930")` 처럼 단일 호출로 endpoint 룩업 → 요청 → 파싱 → 모델 반환을 처리합니다. `_DomesticNamespace`가 `KisClient`에 attribute로 부착되어, 호출자가 `EndpointSpec`이나 raw 페이로드를 만질 필요 없이 사용할 수 있습니다.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `_DomesticNamespace` — `KisClient.domestic` 진입점, 하위 API 인스턴스(`price`, `chart`, `symbols`, `rank`, `analysis`) 조립 |
| `price.py` | `DomesticPriceAPI.current(symbol, *, market="KOSPI", market_div="J"|"NX"|"UN")` → `CurrentPrice` |
| `chart.py` | `DomesticChartAPI.daily/weekly/monthly/yearly(symbol, *, start, end, market, adjusted, max_pages)` → `list[OhlcvBar]` (페이지네이션 자동) |
| `symbols.py` | `DomesticSymbolsAPI.product_info(symbol, *, product_type="300")` → `ProductInfo`, `financial_summary(symbol, *, fid_div_cls_code)` → `FinancialSummary` — Stage 5 |
| `rank.py` | `DomesticRankAPI.volume(market_code, count, *, market=None)` → `list[DomesticVolumeRankItem]` — Stage 5 |
| `analysis.py` | `DomesticAnalysisAPI.investor_flow(symbol, start, end, *, market, market_div, adjusted)` → `list[InvestorFlow]` — Stage 5 |

## For AI Agents

### Working In This Directory
- 모든 메서드는 `async`입니다. `KisClient`가 async context manager 안에 있을 때만 호출 가능합니다.
- 메서드 시그니처 컨벤션: `(symbol: str, *, <keyword-only options>)` — 첫 인자만 positional, 나머지는 모두 keyword.
- `symbol`은 진입 시점에 `.strip().upper()`로 정규화하고 빈 문자열은 `ValueError`로 거부합니다.
- 새 메서드를 추가하면 (1) `endpoints/domestic/<file>.py`에 EndpointSpec 등록 → (2) 이 폴더에 API 클래스 메서드 추가 → (3) `_DomesticNamespace.__init__`에서 인스턴스화.
- 페이지네이션 구현은 `chart.py`의 패턴을 따르세요: 결과를 `dict[timestamp, OhlcvBar]`로 중복 제거 → `max_pages` 가드 → 마지막에 ascending sort.

### Testing Requirements
- `httpx.MockTransport`로 `KisClient.request()`가 호출하는 KIS 응답을 흉내내고, 반환된 모델 인스턴스의 모든 필드를 검증합니다 (`tests/test_stage5_facades.py`, `tests/test_chart.py`).
- 페이지네이션 메서드는 (a) 한 페이지 결과, (b) 여러 페이지 결과, (c) `max_pages` 도달 시 조기 종료 세 케이스를 확인합니다.

### Common Patterns
- 모듈 상단에서 `_SPEC = lookup("domestic.price.current")` 패턴으로 import 시점에 spec을 한 번 조회 — 메서드 호출마다 룩업 비용을 줄입니다.
- `market` 인자는 모델 라벨링용이고, 실제 KIS 분기는 `market_div` (`J`=KRX, `NX`=NXT, `UN`=통합)으로 제어합니다.
- 모든 API 클래스는 `__init__(self, parent: "KisClient")` 패턴으로 부모를 보관하고 `self._parent.request(spec, params=...)`를 호출합니다.

## Dependencies

### Internal
- `kis.endpoints.registry.lookup` — spec 조회
- `kis.models.*`, `kis.parsers.rest` — 파싱/모델

### External
- 없음 (`KisClient`가 `httpx`를 소유).

<!-- MANUAL: 수동 메모는 이 라인 아래에 작성하면 재생성 시 보존됩니다 -->
