# Fractal Research

This package isolates the fractal-label experiment from the old `Fractal`
prototype.

The core idea:

1. Generate lagging supervised labels with a centered rolling window.
2. Build one sample from the candles up to each labeled event.
3. Classify the sample with a small `CNN1D`.

## Labels

Fractal event handling is split into explicit stages:

```text
detect_fractal_events
→ filter_fractal_events
→ fractal_event_segments
→ segment-level filters
```

`detect_fractal_events` returns raw centered-window high/low extrema only:

- raw high: center candle high is the unique max in the odd window
- raw low: center candle low is the unique min in the odd window

`filter_fractal_events` then applies event-level conditions such as near-flat
window removal and optional MA-based filtering. The compatibility wrapper
`compute_fractal_events` runs both steps and marks:

- `0`: fractal low while `short_ma >= long_ma`
- `1`: fractal high while `short_ma >= long_ma`
- `2`: filtered event, usually because `short_ma < long_ma`

The label window is an odd centered window, so label generation uses future candles. This is
valid for supervised training labels, but it is not a live trading signal.

Current labeling rules intentionally avoid ambiguous extrema:

- `window` must be odd; the default is `21`.
- A fractal high/low must be the unique max/min inside the window.
- Near-flat windows are skipped with `min_window_range_pct`.

## Samples

`build_fractal_samples` keeps only candles up to and including the event candle.
By default the model sees these six features:

- open
- high
- low
- close
- short moving average
- long moving average

Each sample is standardized independently, matching the original prototype.

## Plotting

`plot_fractal_events` draws candles with fractal high/low markers using Plotly.
Plotly is used because it provides native candlestick traces, notebook/browser
interactivity, and figure reuse for polling or streaming workflows. The function
returns a `plotly.graph_objects.Figure`; callers decide whether to display it,
write it to HTML, or update the same figure object repeatedly.

```python
from research.fractal import FractalLabelConfig, plot_fractal_events

fig = plot_fractal_events(
    candles,
    label_config=FractalLabelConfig(window=21, short_ma=20, long_ma=120),
    max_candles=300,
    show_filtered=False,
)
fig.show()
```

For live or near-real-time use, pass the previous `figure` and a rolling
`max_candles` value. Only confirmed lagging fractal events can be shown because
the latest `window // 2` candles do not have centered-window labels yet.

### Loading plot data from DuckDB

For FinLabs warehouse data, use `plot_fractal_events_from_warehouse`. It delegates
DuckDB reads to `research.tokenizers.data.load_candles`, so this module does not
duplicate warehouse SQL. Daily bars are loaded from `ohlcv_bars`; minute bars are
loaded from `overseas_minute_bars`.

```python
from kis_cli.storage.warehouse import default_warehouse_file
from research.fractal import plot_fractal_events_from_warehouse

fig = plot_fractal_events_from_warehouse(
    default_warehouse_file(),
    market="NASDAQ",
    symbol="AAPL",
    interval="1m",
    limit=500,
    max_candles=300,
)
fig.show()
```

## Model

`CNN1D` expects `batch x steps x features`. It transposes to
`batch x features x steps` before applying `Conv1d(kernel_size=1)` layers and
adaptive average pooling.

```python
from research.fractal import FractalLabelConfig, build_fractal_samples
from research.fractal.data import Candle
from research.fractal.train import train_cnn1d

candles = [
    Candle(timestamp="2024-01-01", open=1, high=2, low=0.5, close=1.5),
    # ...
]

samples = build_fractal_samples(
    candles,
    max_len=20,
    label_config=FractalLabelConfig(window=21, short_ma=20, long_ma=120),
)
model, history = train_cnn1d(samples)
```

## CLI Plot Command

The plotting helper can also be run as a module. It reads candles from the
local DuckDB warehouse and writes one plot for every confirmed adjacent
`high_to_low` and `low_to_high` fractal segment. SVG files are written under
`research/fractal/event_plots/` by default. Static SVG/PNG/PDF export uses
Plotly Kaleido.

For minute intervals, the command skips segments that cross a large timestamp
gap. This prevents a Friday after-hours candle and the next Monday pre-market
candle from being plotted as one artificial low→high or high→low segment. By
default, the maximum allowed adjacent candle gap is `interval_minutes * 5`.
Override it with `--max-gap-minutes`; daily intervals disable this filter unless
an explicit value is provided.

The command also skips weak segments whose start/end event price change is below
`--min-segment-change-pct`. The default is `3`, so a segment must move at least
3% from the first fractal event price to the second fractal event price.

Segment plots use raw high/low events after event-level filtering, not the
MA-filtered supervised labels. This keeps event detection separate from segment
selection.

```bash
uv run python -m research.fractal.plot_command \
  --market NASDAQ \
  --symbol AAPL \
  --interval 1m \
  --limit 500 \
  --max-candles 300 \
  --max-gap-minutes 5 \
  --min-segment-change-pct 3 \
  --type svg \
  --out research/fractal/event_plots/fractal_AAPL_1m \
  --open
```

Use `--interval 1m` for minute bars or `--interval 1d` for daily bars. Use
`--window 21` or another odd value. Even windows are rejected because fractal
labels use a centered window.

Supported `--type` values: `svg`, `png`, `html`, `pdf`. If `--out` has a different suffix, the selected `--type` wins and the suffix is normalized. The command appends `_high_to_low` and `_low_to_high` to the output base name.
Supported `--type` values: `svg`, `png`, `html`, `pdf`. If `--out` has a
different suffix, the selected `--type` wins and the suffix is normalized. The
command appends `_{transition}_{ordinal:03d}` to the output base name. The ordinal
is counted separately per transition type.

Example outputs:

```text
research/fractal/event_plots/fractal_AAPL_1m_high_to_low_001.svg
research/fractal/event_plots/fractal_AAPL_1m_high_to_low_002.svg
research/fractal/event_plots/fractal_AAPL_1m_low_to_high_001.svg
```
