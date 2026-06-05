<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# overseas (endpoints)

## Purpose
Collection of **EndpointSpec registration modules** for overseas exchange (NAS/NYS/AMS/HKS/TSE/SHS/SZS/HNX/HSX) KIS Open API. Unlike domestic endpoints, KIS does not provide paper-trading TR IDs for most overseas endpoints, so the majority of registered specs have `tr_id_mock=None` and will automatically raise `MockNotSupportedError` when used with `environment="mock"`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Imports `analysis`, `basic_quote`, and `realtime` submodules to trigger spec registration |
| `basic_quote.py` | `[해외주식] 기본시세.xlsx` — `overseas.price.current` (HHDFS00000300, mock=None), `overseas.chart.ohlcv` (FHKST03030100, mock=None), `overseas.chart.dailyprice` (HHDFS76240000, `supports_tr_cont=True`), `overseas.chart.minute` (HHDFS76950200) |
| `analysis.py` | `[해외주식] 시세분석.xlsx` — `overseas.analysis.price_fluct` (HHDFS76260000), `volume_surge` (HHDFS76270000), `volume_power`, `updown_rate`, `new_highlow`, `trade_vol`, etc. (bulk specs, all mock=None) |
| `realtime.py` | `[해외주식] 실시간시세.xlsx` — `overseas.realtime.trades` (HDFSCNT0, WebSocket, mock=None), `overseas.realtime.orderbook` (HDFSASP0, mock=None) |

## For AI Agents

### Working In This Directory
- **Nearly all overseas endpoints have `tr_id_mock=None`**. Verify against the KIS documentation that an endpoint is genuinely mock-unsupported before registering — do not fill in `None` arbitrarily.
- Name convention: `overseas.<group>.<action>` (e.g. `overseas.price.current`, `overseas.chart.minute`, `overseas.analysis.volume_surge`).
- Registration patterns are the same as for domestic:
  - Core endpoints as module variables (`CURRENT_PRICE = register(EndpointSpec(...))`).
  - Bulk specs as a `_SPECS = (...,)` tuple + loop.
- Overseas analysis endpoints accept KIS-specific parameter keys such as `AUTH`, `EXCD`, `GUBN`, `NDAY`, `VOL_RANG` in `required_params`. Register the key names exactly as-is (KIS is strict about case and underscores).
- For endpoints like `overseas.chart.minute` where pagination depends on the response body (`output1.next`) rather than the `tr_cont` header, set `supports_tr_cont=False` and implement body-based branching in the caller (`modules/brokers/kis/overseas/chart.py`).

### Testing Requirements
- For mock-unsupported endpoints, add a one-line regression in `tests/test_kis_package.py` verifying that `tr_id_for("mock")` raises `MockNotSupportedError`.
- For core endpoints (`overseas.price.current`, `overseas.chart.dailyprice`, `overseas.chart.minute`), retrieve metadata via `lookup(...)` and assert `tr_id_real` / `path` match expected values.

### Common Patterns
- State the source Excel workbook in the first line of the module docstring (`"""EndpointSpec registry for '[해외주식] 기본시세.xlsx'."""`).
- WebSocket endpoints follow the same pattern as domestic: `method="POST"` + 5 WebSocket headers + `required_params=("tr_id", "tr_key")`.
- Overseas exchange codes (`EXCD`) are 3-character uppercase as defined by KIS (`NAS`/`NYS`/`AMS`/`HKS`/`TSE`/`SHS`/`SZS`/`HNX`/`HSX`).

## Dependencies

### Internal (within `modules.brokers.kis` only — no other `modules.*` sibling)
- `modules.brokers.kis.endpoints.registry` — `EndpointSpec`, `register`

### External
- None.

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
