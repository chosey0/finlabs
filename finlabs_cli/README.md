# FinLabs CLI

`finlabs_cli` is a new Typer/Rich application for operating the broker SDKs
directly. It is separate from the legacy `kis_cli` application and starts with
account management, token handling, chart requests, and an interactive realtime
session.

Run it locally with:

```bash
uv run python -m finlabs_cli --help
```

No console-script entry point is registered yet. Keep using `python -m
finlabs_cli` until packaging policy changes.

## Scope

Implemented:

| Area | Command | Status |
|------|---------|--------|
| Accounts | `accounts list` | implemented |
| Accounts | `accounts register` | implemented, interactive |
| Accounts | `accounts update` | implemented, interactive |
| Accounts | `accounts delete` | implemented, interactive |
| Auth | `auth status` | implemented |
| Auth | `auth refresh` | implemented |
| Auth | `auth revoke` | implemented; Kiwoom calls revoke API, others clear local cache |
| Chart | `chart domestic` | implemented through Kiwoom SDK |
| Chart | `chart overseas` | implemented through KIS SDK |
| Realtime | `realtime run` | implemented as an interactive foreground session |
| Realtime | `realtime monitor` | placeholder until daemon/IPC exists |

Not implemented yet:

- realtime daemon process
- cross-process realtime monitor/subscribe/unsubscribe commands
- fuzzy symbol search
- symbol master refresh
- persistence of realtime events or chart results
- chart/realtime support through Toss

## Storage

The app uses OS-standard local paths through `platformdirs`.

| Data | Default location |
|------|------------------|
| Accounts | user config dir, `finlabs-cli/accounts.json` |
| Tokens | user cache dir, `finlabs-cli/tokens.json` |

Both files are written with owner-only permissions (`0600`). Accounts currently
store credentials in local JSON. Do not commit these files or copy them into the
repository.

## Commands

### Accounts

```bash
uv run python -m finlabs_cli accounts list
uv run python -m finlabs_cli accounts register
uv run python -m finlabs_cli accounts update
uv run python -m finlabs_cli accounts delete
```

Supported brokers:

- `kis`
- `kiwoom`
- `toss`

Common account fields:

- alias
- broker
- owner name
- environment
- expiration date
- optional account number

Broker credential fields:

| Broker | Credentials |
|--------|-------------|
| KIS | `app_key`, `app_secret`, optional account number |
| Kiwoom | `app_key`, `secret_key` |
| Toss | `client_id`, `client_secret` |

Account password is optional and is not needed for chart or realtime data.

### Auth

```bash
uv run python -m finlabs_cli auth status
uv run python -m finlabs_cli auth refresh --alias kiwoom-main
uv run python -m finlabs_cli auth revoke --alias kiwoom-main
```

`auth refresh` builds the broker SDK client for the selected account and calls
`ensure_token()`. The resulting token is stored in `JsonTokenStore`, which
implements the SDK cache protocol.

`auth revoke` behavior:

- Kiwoom: calls the Kiwoom revoke endpoint, then clears cached tokens.
- KIS/Toss: clears local cached tokens. Their current SDK surfaces do not expose
  a revoke API.

### Chart

Domestic chart data uses Kiwoom SDK:

```bash
uv run python -m finlabs_cli chart domestic --alias kiwoom-main --symbol 005930 --interval daily --base-date 2026-06-17
```

Supported domestic intervals:

| Interval | Kiwoom API |
|----------|------------|
| `tick` | `ka10079` |
| `minute` | `ka10080` |
| `daily` | `ka10081` |
| `weekly` | `ka10082` |
| `monthly` | `ka10083` |
| `yearly` | `ka10094` |

Overseas chart data uses KIS SDK:

```bash
uv run python -m finlabs_cli chart overseas --alias kis-main --symbol AAPL --exchange NAS --interval daily --start 2026-01-01 --end 2026-06-17
```

Supported overseas intervals:

| Interval | KIS API |
|----------|---------|
| `minute` | `HHDFS76950200` |
| `daily` | `HHDFS76240000` |
| `weekly` | `HHDFS76240000` |
| `monthly` | `HHDFS76240000` |

The command prints the most recent rows in a Rich table. It does not persist
results yet.

### Realtime

The MVP realtime flow is foreground and interactive:

```bash
uv run python -m finlabs_cli realtime run --alias kiwoom-main
```

Inside the session, choose:

- Subscribe
- Unsubscribe
- Show subscriptions
- Disconnect

Kiwoom subscriptions:

- `trades` -> `0B`
- `orderbook` -> `0D`

KIS subscriptions:

- overseas trades/orderbook through KIS realtime SDK
- overseas feed uses `feed="realtime"` in this CLI for non-domestic venues

`realtime monitor` is intentionally not a real monitor yet. A separate monitor
command needs a long-running daemon or IPC layer so another process can inspect
the active session.

## Architecture

```text
finlabs_cli/
  commands/     Typer command groups only
  app/          account/token stores, SDK client factory, chart/realtime runners
  models/       CLI-owned account and subscription records
  ui/           Rich console, prompts, tables
```

The broker SDKs remain pure SDK packages. `finlabs_cli` owns:

- account/profile storage
- persistent token cache injection
- prompt flow
- Rich output
- realtime session ownership
- future persistence or event routing policy

The SDKs own only broker transport, authentication protocol, request formatting,
WebSocket protocol handling, and payload parsing.

## Development

```bash
uv run python -m finlabs_cli --help
uv run ruff check finlabs_cli tests/applications/finlabs_cli/test_app.py
uv run python -m pytest tests/applications/finlabs_cli/test_app.py -q
uv run python -m compileall -q finlabs_cli
```

Do not run real broker network calls in unit tests. Use temporary stores and
mock SDK clients/transports.
