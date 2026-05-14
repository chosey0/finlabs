# AGENTS.md

## Project Summary

`FinLabs` is a local-first Python project for brokerage Open API SDKs, market data collection, and future analysis/dashboard tooling. The current implementation focuses on Korea Investment & Securities Open API data collection.

Core goals:

- Provide the current KIS CLI through `python -m kis_cli` during local development.
- Authenticate with KIS REST APIs as the first broker integration.
- Download and normalize KIS symbol masters.
- Retrieve daily/weekly/monthly/yearly and minute OHLCV data.
- Store market data in DuckDB and operational logs in SQLite.
- Optionally mirror selected data to Supabase/PostgreSQL.
- Preserve ordered ingestion, idempotency, and duplicate prevention.

Do **not** add UI, dashboards, chart rendering, trading/order execution, strategies, backtesting, ML, news analysis, or new broker adapters unless explicitly requested for a concrete feature.

## Repository Layout

```text
kis/       KIS SDK: REST/WebSocket clients, endpoint specs, parsers, models
kis_cli/   Current FinLabs KIS CLI application and storage workflows
tests/     Focused unit tests
exports/   CSV sample outputs
README.md  User-facing usage docs
pyproject.toml project metadata and dependencies
```

세부 가이드라인은 각 디렉토리의 AGENTS.md를 참고하세요:

| Directory | AGENTS.md |
|-----------|-----------|
| `kis/` | [kis/AGENTS.md](kis/AGENTS.md) |
| `kis_cli/` | [kis_cli/AGENTS.md](kis_cli/AGENTS.md) |
| `tests/` | [tests/AGENTS.md](tests/AGENTS.md) |
| `exports/` | [exports/AGENTS.md](exports/AGENTS.md) |

Do not create `docs/`, `examples/`, `LICENSE`, or `CHANGELOG.md` unless explicitly requested.

## Architecture Rules

- Keep CLI files thin; delegate business logic to `services/`.
- Put direct KIS REST behavior in `core/`.
- Put database schema, reads, writes, and duplicate prevention in `storage/`.
- Keep path resolution in `kis_cli/config/paths.py`, not `utils/`.
- Use Typer for CLI commands; do not add raw `argparse` commands.
- Keep the current implementation KIS-specific until a concrete new broker adapter is requested.
- Never store credentials, tokens, logs, database files, raw market dumps, or private configs in package source.

## CLI Contract

Local CLI invocation is:

```bash
python -m kis_cli
```

Implemented sub-apps:

```text
config  auth  db  symbols  chart  query  logs
```

Implemented commands include:

```bash
python -m kis_cli config init|add|update|delete|validate
python -m kis_cli auth test|status|clear
python -m kis_cli db init|schema|counts
python -m kis_cli symbols download --market NASDAQ
python -m kis_cli symbols search --query apple
python -m kis_cli chart daily --symbol AAPL --start 2025-01-01 --end 2025-12-31 --save
python -m kis_cli chart minutes --symbol AAPL --interval-minutes 1
python -m kis_cli query ohlcv --symbol AAPL --limit 10
python -m kis_cli query minutes --symbol AAPL --interval-minutes 1
python -m kis_cli logs runs
python -m kis_cli logs api
```

Planned only; do not document as available unless implemented:

```bash
python -m kis_cli price current --symbol AAPL --market NASDAQ
python -m kis_cli stream trades --symbol 005930 --market KRX
python -m kis_cli stream quotes --symbol AAPL --market NAS
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

These paths currently keep the legacy `kis-cli` app name for local data compatibility.
```

Never commit secrets, account numbers, access/refresh tokens, local DB files, logs, raw market data, or private config files. Mask secrets in all CLI output and logs.

## Development Commands

Prefer `uv`:

```bash
uv sync
uv run python -m kis_cli --help
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

`pyproject.toml` is kept for dependency metadata only. Local CLI execution uses `python -m kis_cli`.

Do not add package build configuration, console-script entry points, or build artifacts unless packaging is explicitly requested again.

## Documentation Rules

- Keep `README.md` practical: install, configure, initialize DB, core commands, examples, development commands.
- Use `python -m kis_cli` for local CLI examples in docs.
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
