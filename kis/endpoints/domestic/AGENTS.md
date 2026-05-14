<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# domestic (endpoints)

## Purpose
Collection of **EndpointSpec registration modules** for the domestic (KRX/NXT) KIS Open API. Each file corresponds to one KIS Excel workbook (`.agents/kis-skill/resources/[국내주식] *.xlsx`) and calls `kis.endpoints.registry.register()` at import time to add specs to the global registry. No business logic — pure metadata.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Imports all submodules (`analysis`, `basic_quote`, `rank`, `realtime`, `sector`, `symbol_info`) to trigger spec registration |
| `basic_quote.py` | `[국내주식] 기본시세.xlsx` — `domestic.price.current` (FHKST01010100, mock OK), `domestic.chart.ohlcv` (FHKST03010100, mock OK, `supports_tr_cont=True`) |
| `analysis.py` | `[국내주식] 시세분석.xlsx` — `domestic.analysis.psearch_title/result`, `intstock_grouplist/multprice`, `investor_trade_by_stock_daily`, etc. (bulk specs via `_SPECS` tuple + loop registration) |
| `rank.py` | `[국내주식] 순위분석.xlsx` — `domestic.rank.volume` (FHPST01710000), `fluctuation`, `quote_balance`, etc. (volume/fluctuation/quote-balance rankings) |
| `sector.py` | `[국내주식] 업종_기타.xlsx` — `domestic.sector.inquire_index_price/daily_price/tickprice/timeprice/time_indexchartprice`, etc. (sector index prices) |
| `symbol_info.py` | `[국내주식] 종목정보.xlsx` — `domestic.symbol_info.product_info` (CTPF1604R), `stock_info` (CTPF1002R), `balance_sheet`/`income_statement`/`financial_ratio`/`profit_ratio`, etc. (financial statements) |
| `realtime.py` | `[국내주식] 실시간시세.xlsx` — `domestic.realtime.trades` (H0STCNT0, WebSocket), `domestic.realtime.orderbook` (H0STASP0) |

## For AI Agents

### Working In This Directory
- **All specs must be registered via `register()`** and must run at module import time. Because `endpoints/__init__.py` acts as the import trigger, add any new file to the import list in `__init__.py`.
- Two registration patterns:
  - **Single/few specs**: expose as a module variable (`CURRENT_PRICE = register(EndpointSpec(...))`) — for core endpoints referenced directly from other modules, as in `basic_quote.py` and `realtime.py`.
  - **Bulk specs**: define a `_SPECS = ((name, path, tr_id_real, tr_id_mock, required_params, korean_label), ...)` tuple and call `register()` in a loop at the end of the module — pattern used by `analysis.py`, `rank.py`, `sector.py`, `symbol_info.py`.
- Names must follow the `domestic.<group>.<action>` format without exception.
- Most domestic endpoints share the same real and mock TR IDs, but verify against the KIS spec and enter them accurately if they differ. Use `None` for mock-unsupported endpoints.
- Copy the Korean API name verbatim from the "API 명" column of the original Excel workbook into the last field to maintain traceability.
- WebSocket realtime endpoints follow `method="POST"`, `required_headers=("approval_key", "custtype", "tr_type", "content-type")`, `required_params=("tr_id", "tr_key")`.

### Testing Requirements
- After registering a new endpoint, add a `lookup("domestic.<...>")` regression case in `tests/test_kis_package.py`.
- Verify that duplicate name registration raises `KisConfigError`.

### Common Patterns
- State the source Excel filename in the first line of the module docstring (`"""EndpointSpec registry for '[국내주식] 기본시세.xlsx'."""`) for traceability.
- Mark `supports_tr_cont=True` only for endpoints that support KIS response-header-based pagination via `tr_cont`.
- Keep `required_params` order exactly as in the KIS documentation — do not alphabetize.

## Dependencies

### Internal
- `kis.endpoints.registry` — `EndpointSpec`, `register`

### External
- None.

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
