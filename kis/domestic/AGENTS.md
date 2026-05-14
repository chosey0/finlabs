<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# domestic

## Purpose
High-level client for domestic (KRX/NXT) REST APIs. A single call such as `KisClient.domestic.price.current("005930")` handles endpoint lookup → request → parsing → model return. `_DomesticNamespace` is attached as an attribute of `KisClient`, so callers never need to touch `EndpointSpec` or raw payloads.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `_DomesticNamespace` — `KisClient.domestic` entry point, assembles child API instances (`price`, `chart`, `symbols`, `rank`, `analysis`) |
| `price.py` | `DomesticPriceAPI.current(symbol, *, market="KOSPI", market_div="J"|"NX"|"UN")` → `CurrentPrice` |
| `chart.py` | `DomesticChartAPI.daily/weekly/monthly/yearly(symbol, *, start, end, market, adjusted, max_pages)` → `list[OhlcvBar]` (auto-pagination) |
| `symbols.py` | `DomesticSymbolsAPI.product_info(symbol, *, product_type="300")` → `ProductInfo`, `financial_summary(symbol, *, fid_div_cls_code)` → `FinancialSummary` — Stage 5 |
| `rank.py` | `DomesticRankAPI.volume(market_code, count, *, market=None)` → `list[DomesticVolumeRankItem]` — Stage 5 |
| `analysis.py` | `DomesticAnalysisAPI.investor_flow(symbol, start, end, *, market, market_div, adjusted)` → `list[InvestorFlow]` — Stage 5 |

## For AI Agents

### Working In This Directory
- All methods are `async`. They can only be called while `KisClient` is inside an async context manager.
- Method signature convention: `(symbol: str, *, <keyword-only options>)` — first argument positional only, the rest keyword-only.
- Normalize `symbol` with `.strip().upper()` on entry; reject empty strings with `ValueError`.
- To add a new method: (1) register `EndpointSpec` in `endpoints/domestic/<file>.py` → (2) add API class method in this directory → (3) instantiate in `_DomesticNamespace.__init__`.
- Follow the pagination pattern in `chart.py`: deduplicate results in `dict[timestamp, OhlcvBar]` → enforce `max_pages` guard → sort ascending at the end.

### Testing Requirements
- Use `httpx.MockTransport` to simulate KIS responses for `KisClient.request()`, then assert every field of the returned model instance (`tests/test_stage5_facades.py`, `tests/test_chart.py`).
- Paginating methods require three cases: (a) single-page result, (b) multi-page result, (c) early termination when `max_pages` is reached.

### Common Patterns
- Resolve spec at import time with `_SPEC = lookup("domestic.price.current")` — avoids repeated lookup overhead per call.
- `market` is for model labeling; actual KIS branching uses `market_div` (`J`=KRX, `NX`=NXT, `UN`=unified).
- All API classes follow `__init__(self, parent: "KisClient")` and call `self._parent.request(spec, params=...)`.

## Dependencies

### Internal
- `kis.endpoints.registry.lookup` — spec lookup
- `kis.models.*`, `kis.parsers.rest` — parsing/models

### External
- None (`KisClient` owns `httpx`).

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
