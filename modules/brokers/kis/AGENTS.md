<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# modules/brokers/kis

## Purpose
`modules.brokers.kis` is a pure Python SDK package wrapping overseas-stock data APIs (REST + realtime WebSocket) and domestic-stock (KRX/KOSPI/KOSDAQ) realtime WebSocket APIs from the Korea Investment & Securities Open API. It is responsible only for transport (REST via `httpx` / WebSocket via `websockets`) and payload normalization (frozen dataclass models + parsers). It contains no filesystem, DB, or CLI code. Persistence and user workflows are handled by `modules.orchestration`, `modules.storage`, and thin transport packages such as `kis_cli/`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Public surface exports (`KisClient`, `Credentials`, models, parsers, symbols, exceptions) |
| `client.py` | `KisClient` facade — async context manager, `request(spec, ...)`, `ensure_token()`, `ensure_approval_key()` |
| `config.py` | `Credentials` (with `from_env()` helper), `rest_base_url()`, `websocket_url()` — environment-specific URL mapping |
| `symbols.py` | Overseas symbol master download/parsing (`download_symbol_master`, overseas TSV) |
| `types.py` | Shared Literal types (`Environment`, `Market`, `Interval`, `HttpMethod`, `CustType`) |
| `exceptions.py` | `KisError` hierarchy (`KisAuthError`, `KisApiError`, `KisConfigError`, `KisRealtimeError`, `MockNotSupportedError`) |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `_internal/` | Private transport — `AsyncHttpTransport`, header builders (see `_internal/AGENTS.md`) |
| `auth/` | OAuth token issuance/caching + WebSocket approval key (see `auth/AGENTS.md`) |
| `endpoints/` | `EndpointSpec` registry and domain-specific registration modules (see `endpoints/AGENTS.md`) |
| `models/` | Normalized response dataclass models (see `models/AGENTS.md`) |
| `parsers/` | KIS payload → model conversion (REST + realtime, see `parsers/AGENTS.md`) |
| `overseas/` | High-level client for overseas exchange APIs (see `overseas/AGENTS.md`) |
| `realtime/` | WebSocket realtime session (`RealtimeSession`) — overseas + domestic trades/orderbook (see `realtime/AGENTS.md`) |

## For AI Agents

### Working In This Directory
- This package is a **pure SDK**. Never add filesystem access, KST timestamping, DuckDB/SQLite logic here — those responsibilities belong in `modules.orchestration`, `modules.storage`, or transport packages such as `kis_cli/`.
- `KisClient` must always be used inside an `async with` context. Calling `request()` outside a context raises `RuntimeError`.
- Adding a new endpoint follows this order: (1) register `EndpointSpec` in `endpoints/` → (2) add parser in `parsers/rest.py` → (3) add model in `models/` → (4) expose high-level method in `overseas/`.
- All models are `@dataclass(frozen=True)` and include a `raw: dict[str, Any]` field to preserve the original payload.
- Endpoints not supported in paper-trading are registered with `tr_id_mock=None` — `tr_id_for("mock")` automatically raises `MockNotSupportedError`.

### Testing Requirements
- Never call the real KIS API. Replace the transport with `httpx.MockTransport` or a mock object.
- Parser tests are in `tests/brokers/kis/test_kis_package.py`; high-level methods in `tests/brokers/kis/test_stage5_facades.py`; realtime in `tests/brokers/kis/test_realtime.py`.
- After registering a new endpoint, verify that `lookup("name")` succeeds and that `tr_id_for("real")` / `tr_id_for("mock")` behave as intended.

### Common Patterns
- Async-first design; a sync wrapper is planned as a separate module in Stage 6.
- Token cache key convention: REST token = `f"{environment}:{app_key}"`, WebSocket approval key = `f"ws:{environment}:{app_key}"`.
- `EndpointSpec` is a frozen dataclass holding metadata only — no business logic.
- Decimal/int conversion always happens in parsers; models receive already-converted values.

## Dependencies

### Internal
- Internal imports only — no dependency on `kis_cli` or other `modules.*` siblings. Downstream layers import this SDK, never the reverse.

### External
- `httpx>=0.27.0` — async REST transport
- `websockets>=13.0` — realtime session

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
