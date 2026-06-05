<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# _internal

## Purpose
Internal SDK transport and header builders. As the underscore prefix implies, this is **not a public surface** — do not import from outside `modules.brokers.kis`. External users reach this layer only via `modules.brokers.kis.KisClient.request()`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Private marker docstring |
| `headers.py` | `build_rest_headers()` (Bearer token + tr_id/custtype), `build_websocket_subscribe_message()` (approval_key + tr_type) |
| `http.py` | `AsyncHttpTransport` — `httpx.AsyncClient` wrapper, GET/POST dispatch based on `EndpointSpec`, maps `rt_cd != "0"` to `KisApiError` |

## For AI Agents

### Working In This Directory
- This module is **transport-only**. Never add business logic, parsing, or model conversion here.
- `AsyncHttpTransport` accepts an externally injected `httpx.AsyncClient` or creates its own (tracked via `_owns_client` flag for lifecycle management).
- Header builders accept only frozen `Credentials`. Token issuance logic lives in `modules.brokers.kis.auth.oauth`.
- If a new header key is added in the KIS API spec, add it as an optional parameter to `build_rest_headers` while keeping KIS defaults unchanged.

### Testing Requirements
- Inject responses via `httpx.MockTransport(handler)` and call `AsyncHttpTransport.request()` directly.
- Regression for `rt_cd` error mapping: verify that a `{"rt_cd": "1", "msg_cd": "...", "msg1": "..."}` response becomes `KisApiError(rt_cd=..., msg_cd=..., msg1=...)`.

### Common Patterns
- Standard async context manager: `async with AsyncHttpTransport(...) as transport:` — `__aexit__` closes only the client it owns.
- Dispatches `params=` for GET and `json=` for POST based on `EndpointSpec.method`.

## Dependencies

### Internal (within `modules.brokers.kis` only — no other `modules.*` sibling)
- `modules.brokers.kis.config` — `Credentials`, `rest_base_url`
- `modules.brokers.kis.endpoints.registry` — `EndpointSpec`
- `modules.brokers.kis.exceptions` — `KisApiError`
- `modules.brokers.kis.types` — `CustType`

### External
- `httpx>=0.27.0`

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
