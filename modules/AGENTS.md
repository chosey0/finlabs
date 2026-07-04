<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-06-05 -->

# modules

> **Status: TARGET ARCHITECTURE (partially built).** This document describes the
> intended layout for FinLabs' core domain code. It is the contract new code must
> follow and the destination of an in-progress migration away from legacy CLI
> storage/service code and the warehouse-read logic that used to live in
> `research/tokenizers/data.py`.
>
> **Already built:** broker SDKs for KIS, Kiwoom, Toss, and KRX now live in the
> sibling `broker-modules` repository and are consumed here through the
> `finlabs-brokers` package under the `brokers.*` import namespace.
> This repository keeps shared `modules/domain/` contracts for market data,
> calendar, surge events, and news intelligence, `modules/storage/repositories.py`
> + `modules/orchestration/query.py` (warehouse **reads** — research and dashboard
> now read through these, fixing the inverted dependency), broker adapters for KIS,
> Kiwoom, and Toss, `modules/orchestration/surge_events.py`, and the
> News Intelligence orchestration/storage path under
> `modules/orchestration/news_intelligence.py` and
> `modules/storage/news_intelligence/`.
>
> **Not built yet:** generic market-data `orchestration/{collection,jobs,registry,types}.py`,
> `adapters/brokers/kis/{symbols,price}.py`, a generic market-data warehouse writer,
> app DB logging, and all of `modules/config/`. Where the tree below does not yet
> exist, treat this file as the spec to build against — do not invent a different
> shape.

## Purpose
`modules/` holds the broker-agnostic core of FinLabs as a clean, layered
dependency graph. It exists to fix three structural problems in the current
codebase:

1. **Split read knowledge** — warehouse SQL used to be duplicated across app
   storage code and `research/tokenizers/data.py`.
2. **Inverted dependencies** — `research/*` must not import application packages.
3. **Broker lock-in** — KIS-specific concerns (market codes, intervals, auth)
   are entangled with collection, storage, and logging inside one service file.

The fix is a strict four-layer stack: pure broker SDKs → broker adapters →
orchestration use cases → storage, with `domain` models shared across them.

## Target Layout

Legend: `✓` exists today, `(planned)` not built yet.

```
modules/
  # Broker SDKs are external: finlabs-brokers dependency from broker-modules.
  # They are still imported as brokers.{kis,kiwoom,toss,krx}.


  adapters/
    brokers/                   # SDK ↔ FinLabs canonical model translators
      kis/
        market_data.py         # ✓ KIS chart/OHLCV SDK calls → canonical bars
        mapper.py              # ✓ KIS model → canonical model conversion
        capabilities.py        # ✓ declares what this broker supports
        symbols.py             # (planned) KIS symbol master → canonical symbols
        price.py               # (planned) KIS quote → canonical price
      kiwoom/
        market_data.py         # ✓ Kiwoom chart SDK → News Intelligence candles
        news_intelligence.py   # ✓ Kiwoom chart normalization helpers
        reaction_data.py       # ✓ Kiwoom reaction-label source data
      toss/
        calendar.py            # ✓ Toss calendar → canonical MarketDay
        market_data.py         # ✓ Toss candles → surge DailyPriceBar

  orchestration/               # FinLabs use cases (the "verbs")
    query.py                   # ✓ warehouse reads (broker-agnostic)
    surge_events.py            # ✓ broker-neutral surge extraction + storage handoff
    news_intelligence.py       # ✓ catalog/search/chart/annotation/dataset/export use cases
    collection.py              # (planned) collect-and-store OHLCV / minutes / symbols
    jobs.py                    # (planned) job submit / run / status (in-memory queue)
    registry.py                # (planned) broker name -> adapter resolution
    types.py                   # (planned) command + result DTOs (CollectionResult, ...)

  domain/                      # Pure data contracts, no I/O
    market_data.py             # ✓ CandleBar, CandleSplit
    market_calendar.py         # ✓ MarketDay, TradingSession
    surge.py                   # ✓ DailyPriceBar, SurgeEvent
    news_intelligence.py       # ✓ News Intelligence DTOs and point-in-time contracts
    broker.py                  # ✓ BrokerCapabilities, MarketDataAdapter/SymbolAdapter Protocols
    symbols.py                 # (planned) CanonicalSymbol, Market

  storage/                     # Persistence
    repositories.py            # ✓ the single source of market warehouse-read SQL
    surge_events.py            # ✓ DuckDB surge-event persistence
    news_intelligence/         # ✓ PostgreSQL repositories, schema, catalog, exports, writer
    warehouse.py               # ✓ warehouse path helper; writer still planned
    app_db.py                  # (planned) SQLite app.db: api_logs, ingest_runs

  config/                      # (planned) Profiles, secrets resolution, OS paths
    profiles.py                # (planned)
    resolver.py
    paths.py
```

> Note: `modules/storage/repositories.py` currently holds warehouse **read** SQL
> only (`load_candles`, `list_available_series`). Warehouse **writes** are not
> currently implemented in `modules/storage`; adding them is part of the
> storage-write migration below.

## Layer Roles

### 1. `brokers.*` — pure SDKs from `finlabs-brokers`
Each subpackage is a standalone client for one brokerage.

**Owns:** API calls, authentication, endpoint definitions, request/response
parsing, returning the SDK's own native models.

**Must NOT touch:** DuckDB/SQLite, job management, CLI/Streamlit/FastAPI, ingest
logging, app-level config workflow, or any `modules.*` sibling. A broker SDK is
reusable in isolation and knows nothing about FinLabs.

### 2. `modules/adapters/brokers/*` — broker translators
The layer that makes a broker speak FinLabs' canonical contract.

**Owns:** SDK model → canonical `domain` model conversion; absorbing per-broker
differences in market codes and interval representations; implementing the
common adapter `Protocol`s; declaring broker `capabilities`.

```python
class KisMarketDataAdapter:
    def collect_ohlcv(self, ...) -> tuple[CanonicalOhlcvBar, ...]:
        ...
```

**Must NOT touch:** DuckDB insert, SQLite logging, Streamlit/FastAPI state,
storage at all (see forbidden edges). An adapter is a translator and connector,
nothing more.

### 3. `modules/orchestration/*` — use cases
Where an actual FinLabs operation runs end to end.

**Owns:** turning a CLI/FastAPI/Streamlit request into a unit of work; resolving
config/profile; selecting the right broker adapter via `registry`; calling the
adapter; persisting via `storage`; recording the ingest log; tracking job state;
returning a result summary DTO.

```python
collect_ohlcv_history(
    broker="kis",
    symbol="AAPL",
    interval="1d",
    start="2024-01-01",
    save=True,
)
```

Internal flow:
```
orchestration.collection
  → registry resolves KisMarketDataAdapter
  → adapter.collect_ohlcv(...)            # canonical bars
  → storage.repositories.insert_ohlcv_bars(...)
  → app_db ingest log
  → return CollectionResult
```

`query.py` is broker-agnostic (it reads the warehouse, not a broker), so it lives
in `orchestration`, NOT under any adapter.

### 4. `modules/domain/*` — contracts
Pure dataclasses/Protocols with no I/O. The shared vocabulary every other layer
agrees on. Importable by all layers because it depends on nothing.

### 5. `modules/storage/*` — persistence
DuckDB warehouse + SQLite `app.db`. **`repositories.py` is the single source of
truth for warehouse SQL.** No other module may write raw `SELECT ... FROM
ohlcv_bars`. Storage never imports brokers, adapters, or orchestration.

### 6. `modules/config/*` — environment
Profile loading, secret/DSN resolution, OS-standard paths (`platformdirs`).
KST timestamps and path conventions belong here and must not leak into SDKs.

## Dependency Rules

Allowed direction (top calls down only):

```
finlabs_cli / FastAPI / dashboard
        ↓
modules.orchestration
        ↓
modules.adapters.brokers.{broker}        and  modules.storage
        ↓
brokers.{broker}

modules.domain  ← importable by every layer (depends on nothing)
modules.config  ← used by orchestration (and below only via injection)
```

Forbidden edges (enforce with `tests/architecture/test_boundaries.py`):

| Forbidden | Why |
|-----------|-----|
| `brokers`  → import `adapters` | SDK must stay standalone |
| `brokers`  → import `orchestration` | SDK must stay standalone |
| `brokers`  → import `storage` / `domain` | SDK owns its own models |
| `modules.adapters` → import `storage` | adapters translate, never persist |
| `modules.adapters` → import `orchestration` | wrong direction |
| `modules.storage`  → import `brokers` / `adapters` | storage knows only `domain` |
| `research`         → import application packages / broker internals | use `orchestration.query` |

Storage writes happen **only** in `orchestration`, never in adapters and never
in SDKs.

## Migration Map (current → target)

| Current location | Splits into | Status |
|------------------|-------------|--------|
| `kis/` (top-level SDK) | `broker-modules` / `finlabs-brokers` | ✅ done |
| legacy app chart service | adapter call + mapping → `adapters/brokers/kis/market_data.py` + `mapper.py`; orchestration (select/save/log/result) → `orchestration/collection.py` | 🟡 partial — adapter mapping exists; save/log + `collection.py` still needed |
| legacy app price/symbol services | KIS-specific half → `adapters/brokers/kis/`; save/log half → `orchestration/` | ⬜ not started |
| legacy app query service | `orchestration/query.py` (broker-agnostic) | ✅ done — reads go through `modules.orchestration.query` |
| legacy app job server | `orchestration/jobs.py` | ⬜ not started |
| `research/tokenizers/data.py` warehouse SQL (`_load_daily_rows`, `_load_minute_rows`) | `modules/storage/repositories.py` (single source); `load_candles` becomes a thin adapter over it | ✅ done — `research.tokenizers.data.load_candles` now wraps `modules.orchestration.query.load_candles` |
| legacy app storage | `modules/storage/*` | 🟡 partial — read repository and warehouse path helper moved; writer/app DB still planned |
| legacy app config | `modules/config/*` | ⬜ not started |
| legacy SDK shims | **delete** | ✅ done |
| legacy token cache | fold into broker auth or `modules/config` | ⬜ not started |

Remaining migration fronts: **collection orchestration**, **storage write
migration**, **config migration**, and **job queue migration**. `finlabs_cli/`,
`dashboard/`, and any future FastAPI server should stay thin transports that
only call SDKs directly where appropriate or route through `modules.orchestration`.

## For AI Agents

### Working In This Directory
- Adding a new brokerage = add the pure SDK in the sibling `broker-modules` repository + `adapters/brokers/<name>/` in this repository. Register it in `orchestration/registry.py` once the generic registry exists; until then keep orchestration wiring explicit and scoped.
- Broker-specific knowledge (market codes, interval strings, auth quirks) lives **only** in `adapters/brokers/<name>/`. If you find a `if broker == "kis"` branch in `orchestration`, that is a smell — push it into the adapter or `capabilities.py`.
- All cross-layer data crossing must be a `domain` canonical model, never a broker-native SDK model. Adapters are the only place SDK models are seen.
- Warehouse SQL goes in `storage/repositories.py` and nowhere else. Reads from CLI, dashboard, and research all funnel through `orchestration/query.py`.
- When generic collection orchestration is added, return frozen result DTOs from `orchestration/types.py` (e.g. `CollectionResult`), matching the existing `@dataclass(frozen=True)` convention.

### Testing Requirements
- Each forbidden edge in the table above must have an AST-based assertion in `tests/architecture/test_boundaries.py`. Add the rule in the same PR that creates the layer.
- Adapters are tested with mock SDK responses → assert canonical model output. No network.
- Generic collection orchestration should be tested with a fake adapter (injected via the planned `registry`) + temp DuckDB/SQLite, asserting save + ingest-log + result DTO.
- When `orchestration/jobs.py` is introduced, keep collection work off request coroutines; the worker/job boundary should own any `asyncio.run` or single-writer constraints.

### Common Patterns
- **Dependency injection over imports**: generic market-data orchestration should receive an adapter from the planned `registry`, and `jobs.py` should receive a `runner` + `error_sanitizer` callable when that layer is added.
- Planned market-data ingest flow stays: `start_ingest_run` → body → `record_api_log` → `finish_ingest_run(status=...)`.
- Capabilities, not exceptions, gate unsupported requests (e.g. KIS supports overseas only) — check `adapter.capabilities` before dispatch.

## Naming
`adapters` + `orchestration` is the chosen vocabulary. `orchestration` was kept
over `workflows` / `usecases` / `operations` because it most precisely names the
job: coordinating adapter + storage + logging into one operation. Do not rename
casually — the name is referenced by import paths and boundary tests.

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
