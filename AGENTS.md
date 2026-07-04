# AGENTS.md

## Project Summary

`FinLabs` is a local-first Python project for market data collection, broker adapters, analysis/dashboard tooling, and CLI workflows. Broker SDK source code is maintained in the sibling `broker-modules` repository and consumed here through the `broker-modules` package. The codebase is mid-migration toward a layered, broker-agnostic core under `modules/` (see [modules/AGENTS.md](modules/AGENTS.md)).

Core goals:

- Provide the current FinLabs CLI through `python -m finlabs_cli` during local development.
- Authenticate with KIS REST APIs as the first broker integration.
- Download and normalize KIS symbol masters.
- Retrieve daily/weekly/monthly/yearly and minute OHLCV data.
- Store market data in DuckDB and operational logs in SQLite.
- Optionally mirror selected data to Supabase/PostgreSQL.
- Preserve ordered ingestion, idempotency, and duplicate prevention.

Do **not** add trading/order execution, strategies, backtesting, or ML unless explicitly requested for a concrete feature. The existing Streamlit `dashboard/`, `research/` chart rendering, the planned Kiwoom broker adapter, and the `finlabs_intelligence/` News Intelligence subsystem are explicitly-requested tracks; build only against them when asked, and keep `research/` isolated from SDK/CLI runtime paths. News analysis lives **only** under `finlabs_intelligence/` (see [finlabs_intelligence/README.md](finlabs_intelligence/README.md)); do not leak it into the broker SDK/CLI/DuckDB paths.

## Repository Layout

```text
modules/   Layered broker-agnostic core (target architecture):
             adapters/brokers/{broker} SDK ↔ canonical-model translators
             orchestration/          use cases + warehouse-agnostic reads
             domain/                 canonical data contracts (no I/O)
             storage/                warehouse read repositories
broker-modules/ sibling repository that owns `brokers.*` SDK packages
finlabs_cli/ FinLabs Typer/Rich CLI for broker SDK account, auth, chart, and
             realtime workflows
dashboard/ Streamlit dashboard; thin transport reading via modules.orchestration
finlabs_intelligence/ News Intelligence collection/labeling subsystem: FastAPI
             API + React (bun) web workbench, PostgreSQL-backed. Self-contained
             and isolated from the SDK/CLI/DuckDB paths.
research/  Experimental market representation and tokenizer research
tests/     Focused unit tests
exports/   CSV sample outputs
README.md  User-facing usage docs
pyproject.toml project metadata and dependencies
```

The top-level `kis/` SDK package has been moved out of this repository. Broker SDKs live
in the sibling `broker-modules` repository and are imported as `brokers.*` through
the `broker-modules` dependency.

For detailed guidelines, see the AGENTS.md in each directory:

| Directory | AGENTS.md |
|-----------|-----------|
| `modules/` | [modules/AGENTS.md](modules/AGENTS.md) |
| `finlabs_intelligence/` | [finlabs_intelligence/README.md](finlabs_intelligence/README.md) |
| `research/` | [research/AGENTS.md](research/AGENTS.md) |
| `tests/` | [tests/AGENTS.md](tests/AGENTS.md) |
| `exports/` | [exports/AGENTS.md](exports/AGENTS.md) |

Do not create `docs/`, `examples/`, `LICENSE`, or `CHANGELOG.md` unless explicitly requested.

## Architecture Rules

### Target layered architecture (`modules/`)

New core code follows the layered stack in [modules/AGENTS.md](modules/AGENTS.md):

- **Broker SDK** → `broker-modules` dependency (`brokers.{broker}` import namespace) — pure transport + parsing, zero FinLabs deps. Must not import any FinLabs `modules.*` sibling.
- **Broker adapter** → `modules/adapters/brokers/{broker}/` — translates SDK models into canonical `domain` models; never persists.
- **Use case / orchestration** → `modules/orchestration/` — coordinates adapter + storage + logging into one operation; the only layer that writes.
- **Canonical domain** → `modules/domain/` — pure dataclasses/Protocols, no I/O, importable by every layer.
- **Shared storage (read repository)** → `modules/storage/` — single source of warehouse SQL; CLI, dashboard, and research read through `modules.orchestration.query`.

Dependencies point downward only and broker-specific knowledge (market codes, intervals, auth quirks) lives only in the adapter. Forbidden cross-layer edges are enforced by `tests/architecture/test_boundaries.py`.

### CLI application (`finlabs_cli/`)

`finlabs_cli/` is the interactive Typer/Rich application. It should stay a thin
transport over broker SDKs and future `modules.orchestration` use cases.

- Use Typer for CLI commands; do not add raw `argparse` commands.
- Keep broker-specific code behind the SDK/adapter boundary rather than hard-coding broker assumptions in shared layers.
- Never store credentials, tokens, logs, database files, raw market dumps, or private configs in package source.

## CLI Contract

Local CLI invocation is:

```bash
python -m finlabs_cli
```

Implemented sub-apps:

```text
accounts  auth  chart  realtime
```

Implemented commands include:

```bash
python -m finlabs_cli accounts list
python -m finlabs_cli accounts register
python -m finlabs_cli auth status
python -m finlabs_cli auth refresh --alias kiwoom-main
python -m finlabs_cli chart domestic --alias kiwoom-main --symbol 005930 --interval daily
python -m finlabs_cli realtime run --alias kiwoom-main
```

Planned only; do not document as available unless implemented:

```bash
python -m finlabs_cli realtime monitor
```

## Storage Rules

Market data is DuckDB-first:

- DuckDB warehouse: `warehouse.duckdb`, default under `data_dir()`.
- SQLite app DB: `app.db`, operational logs only.
- Supabase/PostgreSQL: optional mirror, not primary storage.

These rules cover the broker SDK/CLI market-data warehouse. The `finlabs_intelligence/` subsystem is PostgreSQL-first (source of truth via `INTELLIGENCE_DATABASE_URL`) and follows its own storage rules in [finlabs_intelligence/README.md](finlabs_intelligence/README.md).

DuckDB tables and required uniqueness:

```sql
symbols UNIQUE (market, symbol)
ohlcv_bars UNIQUE (market, symbol, interval, timestamp)
overseas_minute_bars UNIQUE (market, symbol, interval_minutes, local_date, local_time)
realtime_ticks UNIQUE (market, symbol, exchange_ts, seq)
```

Supabase/PostgreSQL mirrors use primary keys:

```sql
symbols PRIMARY KEY (market, symbol)
ohlcv_bars PRIMARY KEY (market, symbol, interval, trade_date)
```

Idempotency requirements:

- Use database constraints, not Python-only duplicate checks.
- DuckDB/PostgreSQL append paths should use `ON CONFLICT DO NOTHING`.
- PostgreSQL upsert paths may use `ON CONFLICT (...) DO UPDATE`.
- SQLite is for append-only operational logs; use `INSERT OR IGNORE` only if a unique constraint is added later.
- Realtime/sequential data should preserve exchange and local ingestion order with fields such as `exchange_ts`, `seq`, `received_at`, and `received_seq`.
- Deterministic realtime ordering should prefer `ORDER BY exchange_ts, seq, received_seq`.

## Config and Local Files

Use OS-appropriate user directories via `platformdirs` or equivalent.

Recommended defaults:

```text
Config: ~/.config/finlabs-cli/
Data:   ~/.local/share/finlabs/
Cache:  ~/.cache/finlabs-cli/
Logs:   ~/.local/state/finlabs/
```

Never commit secrets, account numbers, access/refresh tokens, local DB files, logs, raw market data, or private config files. Mask secrets in all CLI output and logs.

## Development Commands

Prefer `uv`:

```bash
uv sync
uv run python -m finlabs_cli --help
uv run python -m pytest
uv run ruff check .
```


## Testing Rules

Add behavior-focused tests for:

- config loading and validation
- CLI argument validation and output formatting
- DB schema creation
- uniqueness constraints and duplicate inserts
- deterministic query ordering
- mocked KIS REST response parsing and error handling

Do not call the real KIS API in unit tests.

When adding a command, manually verify at least one success path and one failure path when practical.

## Project Metadata Rules

`pyproject.toml` is kept for dependency metadata only. Local CLI execution uses `python -m finlabs_cli`.

Do not add package build configuration, console-script entry points, or build artifacts unless packaging is explicitly requested again.

## Documentation Rules

- Keep `README.md` practical: install, configure, initialize DB, core commands, examples, development commands.
- Use `python -m finlabs_cli` for local CLI examples in docs.
- Only document implemented commands as available.
- Clearly mark unfinished features as planned.
- Do not include real secrets, account numbers, or private paths.

## Git and PR Rules

Use concise commit messages such as:

```text
feat: add config validation command
fix: prevent duplicate OHLCV inserts
test: add warehouse uniqueness tests
docs: document db init
```

Keep PRs focused. Include summary, tests/commands run, manual verification, and known limitations.
