<!-- Parent: ../AGENTS.md -->
<!-- Generated: 2026-05-13 | Updated: 2026-05-14 -->

# overseas

## Purpose
High-level client for overseas exchange (NAS/NYS/AMS/HKS/TSE/SHS/SZS/HNX/HSX) REST APIs. Unlike domestic, KIS does not provide paper-trading TR IDs for most overseas endpoints — if a registered spec has `tr_id_mock=None`, using it with `environment="mock"` automatically raises `MockNotSupportedError`.

## Key Files

| File | Description |
|------|-------------|
| `__init__.py` | `_OverseasNamespace` — `KisClient.overseas` entry point, assembles child API instances (`price`, `chart`, `analysis`) |
| `price.py` | `OverseasPriceAPI.current(symbol, *, exchange, market=None)` → `CurrentPrice`. `exchange` is a 3-character KIS code (`NAS`/`NYS`/...) |
| `chart.py` | `OverseasChartAPI.daily(period="D"|"W"|"M")` (HHDFS76240000, KEYB pagination), `minute(interval_minutes=N)` (HHDFS76950200, `output1.next` flag pagination) |
| `analysis.py` | `OverseasAnalysisAPI.volume_surge(exchange, count, *, minutes=0, volume_range="0")` → `list[OverseasVolumeSurgeItem]` — Stage 5 |

## For AI Agents

### Working In This Directory
- Because nearly all endpoints are mock-unsupported, write tests against `environment="real"` and add only a `MockNotSupportedError` regression case for the mock path.
- Overseas methods require both `symbol` and **`exchange`** — unlike domestic, `market` alone cannot distinguish KIS endpoint variants.
- For overseas minute candles (`minute`), derive the `KEYB` token from `local_date + local_time` of the last parsed bar to support bidirectional pagination — maintain the `_derive_minute_keyb()` pattern.
- For overseas daily candles (`daily`), combine backward pagination (`BYMD` decrement) with the `KEYB` token until `start` is reached.
- When adding a new overseas endpoint, verify in the KIS documentation that a mock TR ID genuinely does not exist before keeping `tr_id_mock=None`.

### Testing Requirements
- `tests/test_chart.py` (minute/daily pagination), `tests/test_stage5_facades.py` (analysis.volume_surge), `tests/test_price.py` (current price) — all use mock transports.
- Regression-check that exchange code normalization (`exchange.strip().upper()`) works as expected.

### Common Patterns
- Resolve spec at module level: `_SPEC = lookup("overseas.<...>")`.
- `OverseasExchangeCode = Literal["NAS", "NYS", "AMS", "HKS", "TSE", "SHS", "SZS", "HNX", "HSX"]` for type safety.
- If `market` is `None`, fall back to using `exchange` as the label.

## Dependencies

### Internal
- `kis.endpoints.registry.lookup`
- `kis.models.*`, `kis.parsers.rest`

### External
- None.

<!-- MANUAL: Manually added notes below this line are preserved on regeneration -->
