<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# tests

## Purpose
`pytest`-based unit and integration test suite. Tests do not depend on the real KIS API — they use mock transports and temporary DuckDB/SQLite files to verify success and failure paths. Add regression tests here whenever a new feature is introduced.

## Key Files

| File | Description |
|------|-------------|
| `test_auth.py` | `kis_cli.services.auth` — profile → token issuance/cache flow |
| `test_chart.py` | OHLCV chart collection + DuckDB ingestion + pagination |
| `test_config_init.py` | `python -m kis_cli config init`, profile add/update/delete |
| `test_kis_package.py` | `kis` SDK surface verification — `KisClient`, models, parsers, `EndpointSpec` |
| `test_logs.py` | `python -m kis_cli logs runs/api` — SQLite `app.db` query + filtering |
| `test_price.py` | Current price service function (`get_current_price`) |
| `test_query.py` | `python -m kis_cli query ohlcv/minutes` — DuckDB query + CSV/JSON output |
| `test_realtime.py` | Stage 4 WebSocket session — `RealtimeSession`, subscription messages, frame parsing |
| `test_stage5_facades.py` | Stage 5 high-level methods — `overseas.analysis` |
| `test_storage.py` | DuckDB/SQLite schema creation, unique constraints, ingestion ordering |
| `test_supabase_schema.py` | Supabase DDL SQL generation + `PRIMARY KEY` verification |
| `test_symbols.py` | Overseas symbol master parsing (TSV) + DuckDB upsert |
| `test_tokenizer_features.py` | Candlestick 7D feature extraction and boundary cases |
| `test_tokenizer_data.py` | Tokenizer DuckDB loading and time-based split behavior |
| `test_tokenizer_metrics.py` | Token utilization, transition counts, semantic consistency |

## For AI Agents

### Working In This Directory
- **Never call the real KIS API.** Replace the transport with `httpx.MockTransport`, `unittest.mock.AsyncMock`, or `monkeypatch`.
- Isolate DB tests using the `tmp_path` fixture — never touch the user data directory (current legacy path `~/.local/share/kis-cli/`).
- Validate WebSocket behavior at the parser unit level via `parse_realtime_frame()` — do not start a real connection.
- When a new endpoint is added, add a `lookup("...")` verification in `test_kis_package.py`; follow the `test_stage5_facades.py` pattern for high-level methods.

### Testing Requirements
- Run: `uv run python -m pytest` (or `pytest`)
- Lint: `uv run ruff check .`
- New tests follow `def test_<behavior>():` or `async def test_<behavior>():` (requires `@pytest.mark.asyncio`) naming.

### Common Patterns
- Mock transport: `httpx.MockTransport(handler)` → `httpx.AsyncClient(transport=mock_transport)` → `KisClient(..., http_client=client)`.
- DuckDB unit tests: call `init_warehouse(tmp_path/'wh.duckdb')`, then call repository functions directly. Tokenizer data tests may create a minimal temporary `ohlcv_bars` table.
- Frozen dataclass result comparison: `assert result == ExpectedResult(...)` — all service results are frozen and support equality.
- Write response fixtures as inline dicts where possible — avoid separate JSON files (readability first).

## Dependencies

### Internal
- `kis` — SDK core
- `kis_cli` — FinLabs KIS CLI + storage

### External
- `pytest>=9.0.3` (currently a runtime dep, planned move to `dev` extras)

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
