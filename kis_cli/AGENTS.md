<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# kis_cli

## Purpose
`kis_cli` is the application package responsible for the FinLabs KIS CLI and (for now) its persistence layer. It consumes the pure SDK `modules.brokers.kis` and provides: (1) profile/secret management, (2) DuckDB warehouse + SQLite `app.db` storage, (3) optional Supabase/PostgreSQL mirror, and (4) a Typer-based CLI. Operational concerns such as KST timestamping, file path resolution, and ingestion logging currently live here.

> **Direction: transitional → thin transport.** `kis_cli` is being reshaped into a
> thin transport / legacy app shell over `modules.orchestration`. The collection,
> write-storage, config, and job-queue logic still hosted here is migrating into
> `modules/` (see [modules/AGENTS.md](../modules/AGENTS.md)). The user-facing CLI
> contract (`python -m kis_cli ...`) stays stable across that migration. Do **not**
> grow `kis_cli/services`, `kis_cli/core`, or `kis_cli/storage` as the long-term home
> for new logic — put new use cases in `modules.orchestration` where possible.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Package metadata (`__version__`) |
| `__main__.py` | Entry point for `python -m kis_cli` — delegates to `cli.app:main` |

## Subdirectories

| Directory | Purpose |
|-----------|---------|
| `cli/` | Typer sub-apps (`config`/`auth`/`db`/`symbols`/`chart`/`query`/`logs`) and shared console |
| `config/` | _(transitional)_ Profile-based settings loading + `~/.config/kis-cli/` path resolution; migrates to `modules/config` |
| `core/` | _(transitional)_ Legacy synchronous REST client and file-based token cache (`CachedToken`); slated for deletion or fold-in to `modules.brokers.kis` auth |
| `services/` | _(transitional)_ Use cases bridging CLI ↔ storage (ingestion, auth, chart collection, queries); new use cases belong in `modules.orchestration` |
| `storage/` | _(transitional)_ DuckDB warehouse writer, SQLite `app.db`, Supabase adapter + repositories; warehouse **reads** already moved to `modules.storage`/`modules.orchestration.query` |
| `utils/` | Shared helpers — currently KST timestamps (`now_kst_iso`) |

For detailed guidelines, see the **Repository Layout** and **Common Tasks** sections in the parent [AGENTS.md](../AGENTS.md).

## For AI Agents

### Working In This Directory
- CLI commands always go in `cli/<group>.py`. `app.py` only assembles the root Typer app; business logic must be delegated to `services/`.
- Market data (`symbols`, `ohlcv_bars`, `overseas_minute_bars`, `realtime_ticks`) **must** be routed to the DuckDB warehouse. SQLite `app.db` is reserved for operational logs (`api_logs`/`ingest_runs`) only.
- Some modules in `kis_cli.core.*` are thin shims left after migration to the SDK. New code should use `from modules.brokers.kis import ...` for direct SDK access, or preferably route application work through `modules.orchestration` as it is introduced.
- KST timestamps (`now_kst_iso`) and file paths (`config/paths.py`) belong exclusively in `kis_cli`. Do not let them leak into the SDK.
- Never place secrets, tokens, or DB files inside the package source. All such data must go to OS-standard paths via `platformdirs`.

### Testing Requirements
- Run tests with `pytest` from the `tests/` directory using mock transports and temporary SQLite/DuckDB files — no real KIS API calls.
- New CLI commands require at least one manual success-path and one failure-path verification, plus unit tests in `tests/test_<group>.py` where feasible.
- Regression-check DuckDB unique constraints, `ON CONFLICT DO NOTHING`, and KST ordering.

### Common Patterns
- All service functions return results as frozen `@dataclass` instances (e.g. `ChartHistoryResult`, `AuthTestResult`).
- Ingestion flow: `start_ingest_run` → body → `record_api_log` → `finish_ingest_run(status="success|failed")`.
- Supabase dependency is optional — activated only when the `KISCLI_SUPABASE_DB_DSN` environment variable is set.
- Use `result_table`, `cli_console()`, and `console` from `cli/common.py` to unify Rich output.

## Dependencies

### Internal
- `modules.brokers.kis` — The current FinLabs KIS SDK (`KisClient`, `Credentials`, models, parsers, symbol downloader)

### External
- `typer>=0.12.0` — CLI framework
- `rich>=13.0.0` + `rich-inquirer>=0.1.8` — Console output/prompts
- `duckdb>=1.1.0` — Local warehouse
- `platformdirs>=4.0.0` — OS-standard paths
- `psycopg>=3.3.4` (optional, `[postgres]` extras) — Supabase mirror

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
