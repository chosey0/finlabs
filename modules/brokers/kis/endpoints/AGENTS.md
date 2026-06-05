<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# endpoints

## Purpose
Manages KIS REST/WebSocket endpoint metadata as a **data-driven registry**. `EndpointSpec` stores path, TR IDs (real/mock), required parameters, and pagination support as a frozen dataclass. Domain-specific registration modules call `register()` at import time to add specs to the global registry. No business logic — all consumers retrieve specs via `lookup("name")`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Imports `overseas` submodules to trigger spec registration + re-exports `EndpointSpec`/`lookup`/`names`/`register` |
| `registry.py` | `EndpointSpec` frozen dataclass (`tr_id_for(env)` with `MockNotSupportedError` guard), `_EndpointRegistry` (rejects duplicate registrations), module-level helpers `register`/`lookup`/`names` |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `overseas/` | Overseas exchange endpoint registrations — basic_quote, analysis, realtime (see `overseas/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- Create new endpoints as `EndpointSpec(name=..., method=..., path=..., tr_id_real=..., tr_id_mock=...)` and **call `register()`** to add them to the global registry.
- Names follow the pattern `<domain>.<group>.<action>` (e.g. `overseas.chart.minute`) — duplicates raise `KisConfigError`.
- Set `tr_id_mock=None` for endpoints not supported in paper-trading. `tr_id_for("mock")` will automatically raise `MockNotSupportedError`.
- Mark paginating endpoints with `supports_tr_cont=True` — callers must pass the `tr_cont` response header to the next request header.
- `required_params`/`required_headers` are documentation hints — the current transport does not enforce them at runtime, but populate them accurately from the KIS spec for each new endpoint.
- POST endpoints (especially WebSocket realtime) follow `method="POST"` + `required_headers=("approval_key", "custtype", "tr_type", "content-type")`.

### Testing Requirements
- After registering a new endpoint, add regression cases: `lookup("name")` succeeds, `tr_id_for("real")`/`tr_id_for("mock")` behave correctly.
- Also regression-test that duplicate registration raises `KisConfigError` and that mock-unsupported endpoints raise `MockNotSupportedError`.

### Common Patterns
- Pattern 1 (single spec): expose as a module variable (`CURRENT_PRICE = register(EndpointSpec(...))`) for direct reference from other modules.
- Pattern 2 (bulk specs): define as a `_SPECS = (...,)` tuple and call `register()` in a loop at the end of the module (used by analysis/rank/sector/symbol_info).
- Record the original Korean API name from the KIS Excel workbook in the last field to maintain traceability.

## Dependencies

### Internal (within `modules.brokers.kis` only — no other `modules.*` sibling)
- `modules.brokers.kis.exceptions` — `KisConfigError`, `MockNotSupportedError`
- `modules.brokers.kis.types` — `Environment`, `HttpMethod`

### External
- None (stdlib only).

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
