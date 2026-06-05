<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# models

## Purpose
Collection of **frozen dataclass models** that represent normalized KIS API responses. All models are `@dataclass(frozen=True)` (immutable), and each preserves the original payload in a `raw` field to support debugging, re-parsing, and mirroring. Models hold data only — no business logic.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | Bulk export of all models — `CurrentPrice`, `OhlcvBar`, `OverseasMinuteBar`, `OrderBookLevel`, `OrderBookSnapshot`, `RealtimeTick`, `SymbolRecord`, reference models |
| `quote.py` | `CurrentPrice` — overseas current price snapshot (market, symbol, price, change, OHLV, volume, raw) |
| `ohlcv.py` | `OhlcvBar` (daily/weekly/monthly/yearly candles, interval labels `1d`/`1w`/`1mo`/`1y`), `OverseasMinuteBar` (overseas minute candles, preserves both local exchange time and KST) |
| `symbol.py` | `SymbolRecord` — overseas symbol master entry, `with_downloaded_at()` helper |
| `orderbook.py` | `OrderBookLevel` (single order book level), `OrderBookSnapshot` (full limit order book with exchange_ts/seq) — added in Stage 4 |
| `tick.py` | `RealtimeTick` — WebSocket trade tick (price, volume, bid/ask) + `exchange_ts`/`seq` — added in Stage 4 |
| `reference.py` | `OverseasVolumeSurgeItem` — overseas analysis/ranking model |

## For AI Agents

### Working In This Directory
- **Always** define as `@dataclass(frozen=True)` — mutation breaks SDK design.
- All models carry `raw: dict[str, Any] = field(default_factory=dict)` or `raw: dict[str, Any] | None = None`. Preserving the original payload is an SDK contract.
- Represent financial values as `Decimal | None` (nullable) or `Decimal` (required). Never use `float` (floating-point precision issues).
- Quantities are `int | None` or `int`; timestamps keep the KIS string format — timezone conversion is the caller's responsibility.
- Add new models to `__init__.py`'s `__all__` and export from the package root `modules/brokers/kis/__init__.py` as well.

### Testing Requirements
- Models themselves contain almost no logic, so tests validate instantiation on the **parser** side (`tests/test_kis_package.py`, `tests/test_stage5_facades.py`).
- To maintain equality-based assertions, preserve frozen + hashability of all fields (dict fields are fine via `default_factory`).

### Common Patterns
- Model names are semantic (`CurrentPrice`, `OhlcvBar`); paginated lists are returned as plain `list[Model]` without a separate container model.
- Shared overseas models (`CurrentPrice`, `OhlcvBar`, `SymbolRecord`) include a `market` field to indicate origin.
- Realtime models (`RealtimeTick`, `OrderBookSnapshot`) hold both `received_seq` and `seq` to preserve queue ordering.

## Dependencies

### Internal
- None (does not import other `modules.brokers.kis.*` modules — bottommost layer; no other `modules.*` sibling either).

### External
- stdlib: `dataclasses`, `decimal`, `typing`.

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
