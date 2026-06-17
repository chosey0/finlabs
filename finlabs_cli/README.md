# FinLabs CLI

`finlabs_cli` is a Typer/Rich application for operating the broker SDKs
directly. It starts with account management, token handling, chart requests, and
an interactive realtime session.

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
uv run python -m finlabs_cli chart domestic --alias kiwoom-main --symbol 005930 --interval daily --start-date 2026-01-01 --base-date 2026-06-17
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

Domestic chart pagination stops once the response reaches `--start-date`, then
returns data from `--start-date` through `--base-date`. Start-date formats are:
tick/minute `YYYY-MM-DD HHMMSS`, daily/weekly `YYYY-MM-DD`, monthly `YYYY-MM`,
and yearly `YYYY`. Minute charts accept numeric `--tic-scope` values, matching
Kiwoom's `tic_scope` request field.

Overseas chart data uses KIS SDK:

```bash
uv run python -m finlabs_cli chart overseas --alias kis-main --symbol AAPL --exchange NAS --interval daily --start 2026-01-01 --end 2026-06-17 --max-pages 100
```

Supported overseas intervals:

| Interval | KIS API |
|----------|---------|
| `minute` | `HHDFS76950200` |
| `daily` | `HHDFS76240000` |
| `weekly` | `HHDFS76240000` |
| `monthly` | `HHDFS76240000` |

The command prints the most recent rows in a Rich table. It does not persist
results yet. Overseas daily, weekly, and monthly charts use the KIS continuation
logic with `--max-pages` defaulting to `100`.

### Realtime

The MVP realtime flow is a foreground Textual TUI:

```bash
uv run python -m finlabs_cli realtime run
```

Inside the session, use the fixed controls:

- Account selection
- Subscribe
- Unsubscribe
- Disconnect

The screen is split into a session summary bar, a subscriptions table, an
activity log, and action tabs for subscribe/unsubscribe/session controls. The
subscriptions table updates received `exchange_ts` and received counts while the
input controls stay stable. `--alias` can still be used to preselect the initial
account, but account choice happens inside the TUI. Changing the selected account
does not close existing sessions; subscriptions from multiple accounts remain
visible together with an `Account` column.

Kiwoom subscriptions:

- `trades` -> `0B`
- `orderbook` -> `0D`

KIS subscriptions:

- overseas trades/orderbook through KIS realtime SDK
- overseas feed is selected during subscribe: `delayed` (`D`) or `realtime` (`R`)

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
