# AGENTS.md

## Project Summary

`kis-cli` is a PyPI-ready, CLI-only Python package for collecting Korea Investment & Securities Open API market data.

Core goals:

- Expose the `kiscli` command.
- Authenticate with KIS REST APIs.
- Download and normalize symbol masters.
- Retrieve daily/weekly/monthly/yearly and minute OHLCV data.
- Store market data in DuckDB and operational logs in SQLite.
- Optionally mirror selected data to Supabase/PostgreSQL.
- Preserve ordered ingestion, idempotency, and duplicate prevention.

Do **not** add UI, dashboards, chart rendering, trading/order execution, strategies, backtesting, ML, news analysis, or non-KIS broker abstractions unless explicitly requested.

## Repository Layout

```text
kis_cli/
  cli/       Typer command definitions
  config/    settings, validation, user path resolution
  core/      KIS REST clients, auth, endpoints, parsers, models
  services/  use cases combining core/config/storage
  storage/   DuckDB, SQLite, optional PostgreSQL/Supabase logic
  utils/     shared helpers only; currently time helpers

tests/       focused unit tests
README.md    user-facing usage docs
pyproject.toml packaging and dependencies
```

Do not create `docs/`, `examples/`, `LICENSE`, or `CHANGELOG.md` unless explicitly requested.

## Architecture Rules

- Keep CLI files thin; delegate business logic to `services/`.
- Put direct KIS REST behavior in `core/`.
- Put database schema, reads, writes, and duplicate prevention in `storage/`.
- Keep path resolution in `kis_cli/config/paths.py`, not `utils/`.
- Use Typer for CLI commands; do not add raw `argparse` commands.
- Keep the project KIS-specific.
- Never store credentials, tokens, logs, database files, raw market dumps, or private configs in package source.

## CLI Contract

The command name is always:

```bash
kiscli
```

Implemented sub-apps:

```text
config  auth  db  symbols  chart  query  logs
```

Implemented commands include:

```bash
kiscli config init|add|update|delete|validate
kiscli auth test|status|clear
kiscli db init|schema|counts
kiscli symbols download --market NASDAQ
kiscli symbols search --query apple
kiscli chart daily --symbol AAPL --start 2025-01-01 --end 2025-12-31 --save
kiscli chart minutes --symbol AAPL --interval-minutes 1
kiscli query ohlcv --symbol AAPL --limit 10
kiscli query minutes --symbol AAPL --interval-minutes 1
kiscli logs runs
kiscli logs api
```

Planned only; do not document as available unless implemented:

```bash
kiscli price current --symbol AAPL --market NASDAQ
kiscli stream trades --symbol 005930 --market KRX
kiscli stream quotes --symbol AAPL --market NAS
```

## Storage Rules

Market data is DuckDB-first:

- DuckDB warehouse: `warehouse.duckdb`, default under `data_dir()`.
- SQLite app DB: `app.db`, operational logs only.
- Supabase/PostgreSQL: optional mirror, not primary storage.

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
Config: ~/.config/kis-cli/config.yaml
Data:   ~/.local/share/kis-cli/
Cache:  ~/.cache/kis-cli/
Logs:   ~/.local/state/kis-cli/logs/
```

Never commit secrets, account numbers, access/refresh tokens, local DB files, logs, raw market data, or private config files. Mask secrets in all CLI output and logs.

## Development Commands

Prefer `uv`:

```bash
uv sync
uv run kiscli --help
uv run pytest
uv run ruff check .
uv run python -m build
```

Fallback without `uv`:

```bash
python -m pip install -e .
python -m pytest
python -m build
```

Do not use `pip install -e ".[dev]"` unless a `dev` extras group exists.

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

## Packaging Rules

`pyproject.toml` must keep the CLI entry point:

```toml
[project.scripts]
kiscli = "kis_cli.cli.app:main"
```

Current optional dependency groups:

```toml
[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.2.0"]
all      = ["psycopg[binary]>=3.2.0"]
```

When touching packaging, prefer moving `pytest` and `ruff` out of runtime dependencies into a future `dev` extras group.

## Documentation Rules

- Keep `README.md` practical: install, configure, initialize DB, core commands, examples, development commands.
- Use `kiscli` in docs.
- Only document implemented commands as available.
- Clearly mark unfinished features as planned.
- Do not include real secrets, account numbers, or private paths.

## Git and PR Rules

Use concise commit messages such as:

```text
feat: add config validation command
fix: prevent duplicate OHLCV inserts
test: add warehouse uniqueness tests
docs: document kiscli db init
```

Keep PRs focused. Include summary, tests/commands run, manual verification, and known limitations.
