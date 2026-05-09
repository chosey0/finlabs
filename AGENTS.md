# AGENTS.md

## Project Overview

`kis-cli` is a PyPI-ready Python CLI project for collecting market data from the Korea Investment & Securities Open API.

The package exposes the `kiscli` command and focuses on:

- KIS REST API authentication
- Symbol master download and normalization
- Current price lookup
- Daily/minute OHLCV retrieval
- SQLite-first storage
- PostgreSQL extension support
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
├── docs/
├── tests/
├── examples/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── pyproject.toml
└── AGENTS.md
```

### Package Responsibilities

- `cli/`: CLI command definitions for `kiscli`
- `core/`: KIS REST API logic, including auth, endpoints, headers, clients, models, parsers, and symbol utilities
- `services/`: Application use cases that combine `core/`, `storage/`, and config
- `storage/`: SQLite/PostgreSQL schema, database adapters, repositories, and duplicate-prevention logic
- `config/`: Settings loading, validation, and config file initialization
- `utils/`: Shared helpers for paths, logging, time, and I/O

Keep CLI command files thin. Business logic belongs in `services/`. Direct KIS REST API behavior belongs in `core/`. Database logic belongs in `storage/`.

---

## Implementation Guidelines

- Build the project as a PyPI-ready Python package named `kis-cli`.
- Expose the CLI entry point as `kiscli`.
- Use `kis_cli/` as the main package directory.
- Keep the project KIS-specific; do not add unnecessary broker abstraction.
- Implement KIS REST API features directly under `core/`.
- Store data in SQLite first, with PostgreSQL support designed as an extension.
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

Preferred MVP commands:

```bash
kiscli config init
kiscli config add
kiscli config update
kiscli config delete
kiscli config validate
kiscli auth test
kiscli db init
kiscli symbols download --market NASDAQ
kiscli symbols search --query apple
kiscli price current --symbol AAPL --market NASDAQ
kiscli chart daily --symbol AAPL --start 2025-01-01 --end 2025-12-31 --save
kiscli query ohlcv --symbol AAPL --interval 1d --limit 10
```

Do not document commands as available unless they are implemented or clearly marked as planned.

### CLI Framework

Use `typer` as the CLI framework.

- Define the root app in `kis_cli/cli/app.py`.
- Keep `kis_cli/cli/app.py` limited to root Typer app assembly and sub-app registration.
- Group subcommands with Typer sub-apps such as `config`, `auth`, `db`, `symbols`, `price`, `chart`, `logs`, `stream`, and `query`.
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
5. SQLite-first compatibility

### Recommended Tables

- `symbols`
- `ohlcv_bars`
- `realtime_ticks`
- `api_logs`
- `ingest_runs`

### Duplicate Prevention

Use database-level constraints.

Examples:

```sql
UNIQUE (market, symbol)
```

```sql
UNIQUE (market, symbol, interval, timestamp)
```

For realtime ticks:

```sql
UNIQUE (market, symbol, exchange_ts, seq)
```

or, if a stable trade identifier exists:

```sql
UNIQUE (market, symbol, trade_id)
```

### Ordered Ingestion

For realtime or sequential data, preserve both exchange order and local ingestion order.

Recommended fields:

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

SQLite:

```sql
INSERT OR IGNORE INTO ...
```

PostgreSQL:

```sql
INSERT INTO ...
ON CONFLICT (...) DO NOTHING;
```

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

Provide examples under `examples/`, such as:

```text
examples/config.yaml.example
```

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
python -m pip install -e ".[dev]"
python -m pytest
python -m build
```

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
kiscli price current --symbol AAPL --market NASDAQ
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

1. Prefer SQLite-compatible schema and SQL first.
2. Add PostgreSQL-specific behavior only when needed and keep it isolated.
3. Enforce duplicate prevention with database constraints, not only Python-side checks.
4. Preserve ingestion order using explicit fields such as `received_seq`, `exchange_ts`, and `received_at` where applicable.
5. Use idempotent writes such as `INSERT OR IGNORE` for SQLite or `ON CONFLICT DO NOTHING` for PostgreSQL.
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

Recommended optional dependency groups:

```toml
[project.optional-dependencies]
postgres = [...]
realtime = [...]
dev = [...]
all = [...]
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
