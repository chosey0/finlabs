# AGENTS.md

## Project Overview

`kis-cli` is a PyPI-ready Python CLI project for collecting market data from the Korea Investment & Securities Open API.

The package exposes the `kiscli` command and focuses on:

- KIS REST API authentication
- Symbol master download and normalization
- Daily/minute OHLCV retrieval
- Local DuckDB warehouse for market data, SQLite `app.db` for operational logs
- Optional Supabase / PostgreSQL mirror
- Ordered ingestion
- Duplicate prevention
- CLI-based querying and export

This project is intentionally CLI-only. Do not add UI, desktop app, web dashboard, chart rendering, trading/order execution, or candle-structure analysis unless explicitly requested.

---

## Repository Layout

```text
kis-cli/
├── kis_cli/
│     ├── __init__.py
│     ├── __main__.py
│     ├── cli/
│     ├── config/
│     ├── core/
│     ├── storage/
│     ├── services/
│     └── utils/
├── tests/
├── README.md
├── pyproject.toml
└── AGENTS.md
```

`docs/`, `examples/`, `LICENSE`, and `CHANGELOG.md` do not exist yet. Add them only when explicitly requested.

### Package Responsibilities

- `cli/`: CLI command definitions for `kiscli`
- `core/`: KIS REST API logic, including auth, endpoints, headers, clients, models, parsers, and symbol utilities
- `services/`: Application use cases that combine `core/`, `storage/`, and config
- `storage/`: DuckDB warehouse for market data, SQLite `app.db` for operational logs, optional Supabase/PostgreSQL mirror; database adapters, repositories, and duplicate-prevention logic live here
- `config/`: Settings loading, validation, and config file initialization
- `utils/`: Cross-cutting helpers shared across layers. Today this is limited to `time.py` (timestamp formatting). Path resolution lives in `kis_cli/config/paths.py`, not in `utils/`. Add new utility modules here only when a helper is genuinely shared by multiple top-level packages and does not belong in `config/`, `core/`, `services/`, or `storage/`.

Keep CLI command files thin. Business logic belongs in `services/`. Direct KIS REST API behavior belongs in `core/`. Database logic belongs in `storage/`.

---

## Implementation Guidelines

- Build the project as a PyPI-ready Python package named `kis-cli`.
- Expose the CLI entry point as `kiscli`.
- Use `kis_cli/` as the main package directory.
- Keep the project KIS-specific; do not add unnecessary broker abstraction.
- Implement KIS REST API features directly under `core/`.
- Store market data in the local DuckDB warehouse (`warehouse.duckdb`) and operational logs in the local SQLite `app.db`. Supabase / PostgreSQL is an optional remote mirror, not the primary store.
- Prioritize ordered ingestion and duplicate prevention using database constraints.
- Exclude UI, chart rendering, trading/order execution, and candle-structure analysis from the initial scope.
- Keep CLI commands simple, composable, and script-friendly.
- Do not store API keys, secrets, tokens, logs, or database files inside the package source.
- Use OS-appropriate user directories for config, cache, data, and logs.
- Use `pyproject.toml` for packaging, dependencies, and the CLI script entry point.
- Use Typer for CLI command definitions under `kis_cli/cli/`; do not implement new CLI commands with raw `argparse`.
- Make PostgreSQL and realtime/WebSocket features optional dependencies if added later.
- Add focused tests for config loading, DB schema creation, duplicate prevention, and REST response parsing.

---

## CLI Naming

The CLI command must start with:

```bash
kiscli
```

Implemented sub-apps (registered in `kis_cli/cli/app.py`):

```text
config   auth   db   symbols   chart   query   logs
```

Implemented commands:

```bash
# config
kiscli config init
kiscli config add
kiscli config update
kiscli config delete
kiscli config validate

# auth
kiscli auth test
kiscli auth status
kiscli auth clear

# db
kiscli db init
kiscli db schema
kiscli db counts

# symbols
kiscli symbols download --market NASDAQ
kiscli symbols search --query apple

# chart (history / daily / weekly / monthly / yearly / minutes)
kiscli chart daily --symbol AAPL --start 2025-01-01 --end 2025-12-31 --save
kiscli chart minutes --symbol AAPL --interval-minutes 1

# query (DuckDB warehouse)
kiscli query ohlcv --symbol AAPL --limit 10
kiscli query minutes --symbol AAPL --interval-minutes 1

# logs (SQLite app.db)
kiscli logs runs
kiscli logs api
```

Planned (not yet implemented — do not document as available):

```bash
kiscli price current --symbol AAPL --market NASDAQ
kiscli stream trades --symbol 005930 --market KRX
kiscli stream quotes --symbol AAPL --market NAS
```

Do not document commands as available unless they are implemented or clearly marked as planned.

### CLI Framework

Use `typer` as the CLI framework.

- Define the root app in `kis_cli/cli/app.py`.
- Keep `kis_cli/cli/app.py` limited to root Typer app assembly and sub-app registration.
- Group subcommands with Typer sub-apps. Implemented today: `config`, `auth`, `db`, `symbols`, `chart`, `query`, `logs`. Planned: `price`, `stream`.
- Put command implementations in the matching `kis_cli/cli/<group>.py` module. Do not add command functions directly to `app.py`.
- Keep command functions thin; delegate behavior to `services/`, `config/`, `core/`, and `storage/`.
- Prefer typed options and explicit help text.
- Convert expected user errors into `typer.BadParameter` or `typer.Exit` with clear messages.
- Do not print secrets or unmasked credential values from any Typer command.

---

## Storage Requirements

Storage must prioritize:

1. Ordered ingestion
2. Duplicate prevention
3. Idempotent writes
4. Deterministic querying
5. DuckDB-first compatibility for market data

### Storage Layout

The project uses two local databases plus an optional remote mirror:

- **DuckDB warehouse** (`warehouse.duckdb`, default under `data_dir()`): market data.
  - Tables: `symbols`, `ohlcv_bars`, `overseas_minute_bars`, `realtime_ticks`.
  - Defined in `kis_cli/storage/warehouse.py`.
- **SQLite app database** (`app.db`, default under `data_dir()`): operational logs.
  - Tables: `api_logs`, `ingest_runs`.
  - Defined in `kis_cli/storage/app_db.py`.
- **Supabase / PostgreSQL** (optional): remote mirror selected via `KIS_SUPABASE_DSN` (or equivalent).
  - Tables: `symbols`, `ohlcv_bars` (see `kis_cli/storage/supabase_schema.py`).
  - Used for upsert/mirroring; not the primary store.

Do not introduce a generic "SQLite-first" path for market data. Market data goes to the DuckDB warehouse; only operational logs and lightweight state belong in `app.db`.

### Duplicate Prevention

Enforce uniqueness with database-level constraints, not Python checks.

DuckDB warehouse:

```sql
-- symbols
UNIQUE (market, symbol)

-- ohlcv_bars
UNIQUE (market, symbol, interval, timestamp)

-- overseas_minute_bars
UNIQUE (market, symbol, interval_minutes, local_date, local_time)

-- realtime_ticks
UNIQUE (market, symbol, exchange_ts, seq)
```

Supabase mirror uses `PRIMARY KEY` instead of `UNIQUE`:

```sql
-- symbols
PRIMARY KEY (market, symbol)

-- ohlcv_bars
PRIMARY KEY (market, symbol, interval, trade_date)
```

If a stable trade identifier becomes available for realtime data, prefer `UNIQUE (market, symbol, trade_id)`.

### Ordered Ingestion

For realtime or sequential data, preserve both exchange order and local ingestion order.

Recommended fields on realtime tables:

```text
exchange_ts
received_at
received_seq
seq
```

Recommended query order:

```sql
ORDER BY exchange_ts, seq, received_seq
```

### Idempotent Inserts

DuckDB (warehouse): use `ON CONFLICT DO NOTHING`. DuckDB honors `UNIQUE` constraints declared in `CREATE TABLE`.

```sql
INSERT INTO ohlcv_bars (...)
VALUES (...)
ON CONFLICT DO NOTHING;
```

SQLite (`app.db`): only used for append-only operational logs (`api_logs`, `ingest_runs`) keyed by `INTEGER PRIMARY KEY AUTOINCREMENT`, so there is normally nothing to deduplicate. If a unique constraint is added later, use `INSERT OR IGNORE`.

Supabase / PostgreSQL: `ON CONFLICT (...) DO NOTHING` for append paths, `ON CONFLICT (...) DO UPDATE SET ...` for upserts (see `upsert_supabase_symbols`).

Avoid Python-only duplicate checks. They are not sufficient.

---

## Configuration and Local Files

Do not place user-specific files inside `kis-cli/`.

Use OS-appropriate user directories.

Recommended defaults:

```text
Config: ~/.config/kis-cli/config.yaml
Data:   ~/.local/share/kis-cli/
Cache:  ~/.cache/kis-cli/
Logs:   ~/.local/state/kis-cli/logs/
```

On Windows, use platform-appropriate app data directories.

Use `platformdirs` or an equivalent lightweight approach.

Never commit:

- API keys
- API secrets
- account numbers
- access tokens
- refresh tokens
- local SQLite files
- logs
- raw market data dumps
- private config files

An `examples/` folder is not part of the repository today. If example configs are needed, prefer documenting the shape inline in `README.md` rather than committing a separate `examples/config.yaml.example`. The CLI itself generates a starter config via `kiscli config init`.

---

## Build and Development Commands

Use the repository’s package manager workflow. This project is expected to be compatible with `uv`.

Typical commands:

```bash
uv sync
```

```bash
uv run kiscli --help
```

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run python -m build
```

If `uv` is not available, use the equivalent Python tooling:

```bash
python -m pip install -e .
python -m pytest
python -m build
```

Note: `pyproject.toml` does not currently expose a `dev` extras group, so `pip install -e ".[dev]"` will fail. Use plain `-e .` until a `dev` group is added (see Packaging Guidelines).

---

## Testing Instructions

Add tests for behavior, not just implementation details.

Focus on:

- Config file loading and validation
- CLI argument validation
- DB schema creation
- Unique constraints
- Duplicate inserts
- Deterministic ordering
- KIS REST response parsing
- Error handling for failed API responses
- Output formatting for table, JSON, or CSV modes

Do not call the real KIS API in unit tests.

Use mocked HTTP responses for API behavior.

Manual verification is still recommended for API integration commands, especially:

```bash
kiscli auth test
kiscli chart daily --symbol AAPL --start 2025-01-01 --end 2025-12-31
```

When adding a command, manually verify at least:

- one successful path
- one failure path

---

## Common Tasks

### Add a CLI Command

1. Define the command contract clearly: command name, arguments, options, output format, and failure behavior.
2. Place command definitions under the matching `kis_cli/cli/<group>.py` module.
3. Keep CLI files thin; delegate business logic to `services/`.
4. Use `core/` only for direct KIS REST API behavior such as auth, endpoints, headers, clients, and parsers.
5. Use `storage/` for database reads, writes, schema creation, and duplicate-prevention logic.
6. Add focused tests when the command includes validation, branching, database writes, formatted output, or error handling.
7. Manually verify at least one success path and one failure path when applicable.

### Add or Change KIS REST API Features

1. Define the target KIS endpoint, required TR ID, request parameters, headers, and expected response shape.
2. Add or update endpoint metadata in `core/endpoints.py`.
3. Implement request construction in `core/client.py` or a focused `core/` module.
4. Normalize raw KIS responses in `core/parser.py`.
5. Keep API credentials, access tokens, and environment settings outside source code.
6. Add tests using mocked responses rather than calling the real API in unit tests.
7. Verify manually with `kiscli auth test` or the relevant CLI command.

### Add Storage Logic

1. Route market data (symbols, OHLCV, minute bars, realtime ticks) to the DuckDB warehouse in `kis_cli/storage/warehouse.py`. Route operational logs (`api_logs`, `ingest_runs`) to SQLite `app.db` in `kis_cli/storage/app_db.py`.
2. Add Supabase / PostgreSQL behavior only when remote mirroring is explicitly requested, and keep it isolated in `kis_cli/storage/supabase*.py`.
3. Enforce duplicate prevention with database constraints (`UNIQUE` for DuckDB, `PRIMARY KEY` for Supabase), not only Python-side checks.
4. Preserve ingestion order using explicit fields such as `received_seq`, `exchange_ts`, and `received_at` where applicable.
5. Use idempotent writes: `ON CONFLICT DO NOTHING` for DuckDB and PostgreSQL, `INSERT OR IGNORE` only if a unique constraint is added to `app.db`.
6. Add tests for schema creation, unique constraints, duplicate inserts, and deterministic query ordering.

### Add Dependencies

1. Confirm the dependency is necessary for the requested behavior.
2. Prefer lightweight, well-maintained dependencies suitable for PyPI distribution.
3. Keep optional features behind optional dependencies, for example PostgreSQL or realtime/WebSocket support.
4. Update `pyproject.toml` through the repository’s package manager workflow.
5. Re-run the smallest command or test that imports or exercises the dependency.
6. Avoid adding dependencies for functionality that can be handled cleanly with the standard library.

### Document Usage

1. Keep `README.md` practical: installation, configuration, database setup, core commands, examples, and development commands.
2. Use the final CLI name `kiscli` in all documentation.
3. Match documented commands to commands that were actually implemented or manually verified.
4. Document where config, cache, data, and logs are stored.
5. Do not include real API keys, secrets, tokens, account numbers, or private paths in examples.
6. Clearly mark unfinished features as planned rather than available.

---

## Code Style Guidelines

- Prefer clear, typed Python code.
- Use type hints for public functions and service-layer functions.
- Keep functions small and purpose-specific.
- Avoid hidden global state.
- Avoid hardcoded paths.
- Avoid hardcoded KIS credentials.
- Prefer explicit error messages over silent failures.
- Prefer deterministic output for CLI commands.
- Use timezone-aware datetimes where possible.
- Normalize external API responses before passing data into storage.
- Keep parsing logic separate from HTTP request logic.

---

## Packaging Guidelines

This project should remain PyPI-ready.

`pyproject.toml` should define:

- package metadata
- runtime dependencies
- optional dependencies
- dev dependencies
- CLI script entry point

Required script entry point:

```toml
[project.scripts]
kiscli = "kis_cli.cli.app:main"
```

Current optional dependency groups in `pyproject.toml`:

```toml
[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.2.0"]
all      = ["psycopg[binary]>=3.2.0"]
```

Recommended next steps for `pyproject.toml` (do when touching packaging):

1. **Move `pytest` and `ruff` out of runtime `dependencies` into a new `dev` extras group.** They are currently declared as runtime deps, which bloats the installed package.
2. **Add `realtime = [...]` extras** when WebSocket support is implemented.
3. **Keep `all` as the union** of optional groups (currently only `postgres`).

Target shape:

```toml
[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.2.0"]
realtime = [...]   # add when stream commands ship
dev      = ["pytest>=9.0.3", "ruff>=0.15.12"]
all      = ["psycopg[binary]>=3.2.0"]
```

Before packaging, verify:

```bash
uv run pytest
uv run ruff check .
uv run python -m build
```

Do not include local data, logs, config files, or secrets in the built package.

---

## Security Considerations

This project handles sensitive API credentials.

Agents must not:

- print secrets in logs
- commit real config files
- embed credentials in tests
- store tokens in the package directory
- include private account information in examples
- expose raw exception output that contains secrets

Mask sensitive values in logs and CLI output.

Example:

```text
app_key: abcd********wxyz
```

Do not implement trading/order execution unless explicitly requested and reviewed separately.

---

## Git and Pull Request Guidelines

Use concise, descriptive commit messages.

Preferred style:

```text
feat: add config validation command
fix: prevent duplicate OHLCV inserts
test: add SQLite unique constraint tests
docs: document kiscli db init
refactor: move KIS parser into core
```

Pull requests should include:

- summary of changes
- commands run
- tests added or updated
- manual verification steps
- any known limitations

Do not mix unrelated changes in one pull request.

---

## Out of Scope Unless Explicitly Requested

Do not add the following by default:

- PySide6 UI
- web dashboard
- chart rendering
- auto trading
- order execution
- strategy engine
- backtesting engine
- candle-structure analysis
- machine learning models
- news analysis
- broker abstraction for non-KIS brokers

Keep the initial product focused on reliable CLI-based KIS REST data collection and storage.

---

## Final Development Priority

Work in this order unless the user requests otherwise:

```text
kis-cli package structure
→ kiscli entry point
→ config management
→ SQLite schema
→ KIS authentication
→ symbol download
→ REST current price
→ REST OHLCV retrieval
→ duplicate-safe storage
→ CLI query commands
→ PostgreSQL extension
→ realtime/WebSocket extension
```
