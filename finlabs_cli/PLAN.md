# FinLabs CLI Plan

This plan tracks the `finlabs_cli` application. It treats broker SDKs as
already-existing lower-level libraries.

## Goal

Build a Typer/Rich CLI that can operate FinLabs broker SDKs with a clean
application boundary:

- account and credential registration
- token refresh/status/revoke
- domestic and overseas chart retrieval
- realtime WebSocket operation with dynamic subscriptions
- later: daemonized realtime control and persistence sinks

## Current State

Implemented:

- root Typer app: `python -m finlabs_cli`
- Rich output and rich-inquirer prompts
- `AccountStore` backed by local JSON
- `JsonTokenStore` implementing broker SDK cache protocols
- broker client factory for KIS, Kiwoom, Toss
- account commands: list/register/update/delete
- auth commands: status/refresh/revoke
- chart commands:
  - Kiwoom domestic chart
  - KIS overseas chart
- realtime command:
  - interactive foreground session
  - dynamic subscribe/unsubscribe inside the same process
- smoke/unit tests for app load, account store, token store, Kiwoom client factory

Known limitations:

- credentials are stored in local JSON, not system keychain
- no symbol fuzzy search yet
- no symbol master refresh yet
- chart results are printed only
- realtime events are printed only
- `realtime monitor` is a placeholder because there is no daemon/IPC
- no Toss chart/realtime command support yet

## Design Constraints

- The CLI must not push application concerns into `modules.brokers.*`.
- SDKs own broker protocol and parsing only.
- CLI commands stay thin; business rules belong in `finlabs_cli.app`.
- Account fields must remain broker-aware. Do not force KIS/Kiwoom/Toss into a
  single flat credential schema.
- Real broker APIs must not be called in unit tests.
- Secrets, tokens, account files, local DB files, and logs must never be stored
  in repository source.

## Milestones

### 1. Harden The MVP

Status: next.

Tasks:

- Add non-interactive options to `accounts register` for scripted setup.
- Validate account expiration date format.
- Validate broker-specific required credential keys before saving.
- Add duplicate subscription prevention in `RealtimeManager`.
- Add graceful error rendering for SDK exceptions.
- Add tests for account update/delete and auth status rendering.

Exit criteria:

- All implemented commands have non-network tests for success and common failure
  paths.
- Invalid account files fail with actionable errors.

### 2. Symbol Search

Status: planned.

Tasks:

- Define `SymbolSearchProvider` in `finlabs_cli.app.symbol_search`.
- Add local symbol index storage.
- Support KIS overseas symbol search from existing KIS symbol master APIs.
- Add Kiwoom domestic symbol source before enabling fuzzy search for domestic
  chart/realtime prompts.
- Replace raw ticker text prompts with search prompts where a provider exists.

Exit criteria:

- `chart domestic` and `chart overseas` can resolve ticker/company text through
  local symbol indexes.
- Missing symbol index produces a clear instruction to refresh symbols.

### 3. Chart Output Sinks

Status: planned.

Tasks:

- Add `sinks/console.py`, `sinks/jsonl.py`, and optional `sinks/duckdb.py`.
- Add `--output table|json|jsonl`.
- Add `--save` only after a destination schema is chosen.
- Keep broker-native SDK models out of long-term storage; convert at app/adapter
  boundary first.

Exit criteria:

- Chart commands can print tables and export JSONL without hitting storage.
- Persistence has tests for duplicate prevention before DuckDB write support
  becomes default.

### 4. Realtime Interactive UX

Status: planned.

Tasks:

- Prevent duplicate active subscriptions.
- Add current subscription table refresh after each action.
- Add event display modes: compact, raw, JSONL.
- Add event throttling or rolling table mode for high-volume feeds.
- Add clean shutdown on Ctrl-C.

Exit criteria:

- A foreground realtime session can be operated without restarting the process.
- Subscribe/unsubscribe state stays consistent with SDK calls.

### 5. Realtime Daemon And IPC

Status: planned.

Tasks:

- Add a long-running local daemon process.
- Choose IPC mechanism: local HTTP on loopback, Unix domain socket, or stdio RPC.
- Add process lock and state file.
- Implement cross-process commands:
  - `realtime start`
  - `realtime stop`
  - `realtime monitor`
  - `realtime subscribe`
  - `realtime unsubscribe`
- Persist session state and subscription snapshots for monitor display.

Exit criteria:

- `realtime monitor` can inspect sessions created by another process.
- subscribe/unsubscribe commands can modify a running session.
- daemon shutdown unsubscribes all active subscriptions before closing sockets.

### 6. Credential Security

Status: planned.

Tasks:

- Evaluate system keychain integration.
- Move secrets from account JSON to keychain-backed references where available.
- Keep file-only fallback for headless/dev environments.
- Add migration path from current JSON format.

Exit criteria:

- New accounts store credentials outside plain JSON by default on supported
  platforms.
- Existing account files continue to work with a warning/migration path.

### 7. Broker Coverage

Status: planned.

Tasks:

- Add Toss chart command if SDK candle semantics map cleanly to CLI intervals.
- Add broker capability matrix.
- Disable unsupported menu choices rather than failing late.
- Keep broker-specific prompts in provider classes, not command functions.

Exit criteria:

- Command availability follows broker capability declarations.
- Unsupported actions are hidden or clearly marked before execution.

## Verification Matrix

Run for normal changes:

```bash
uv run python -m finlabs_cli --help
uv run ruff check finlabs_cli tests/applications/finlabs_cli/test_app.py
uv run python -m pytest tests/applications/finlabs_cli/test_app.py -q
uv run python -m compileall -q finlabs_cli
```

Run when broker SDK integration changes:

```bash
uv run python -m pytest tests/architecture/test_boundaries.py -q
uv run ruff check modules/brokers/kis modules/brokers/kiwoom modules/brokers/toss finlabs_cli
```

Manual network verification, only with real credentials:

```bash
uv run python -m finlabs_cli auth refresh --alias <alias>
uv run python -m finlabs_cli chart domestic --alias <kiwoom> --symbol 005930 --interval daily --base-date 2026-06-17
uv run python -m finlabs_cli chart overseas --alias <kis> --symbol AAPL --exchange NAS --interval daily --start 2026-01-01 --end 2026-06-17
uv run python -m finlabs_cli realtime run --alias <kiwoom-or-kis>
```

## Non-Goals For Now

- order execution
- portfolio/account balance operations
- strategy/backtesting workflows
- GUI dashboard integration
- distributed realtime ingestion
