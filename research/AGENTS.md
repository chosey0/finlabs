<!-- Parent: ../AGENTS.md -->

# research

## Purpose
`research/` contains experimental market-representation work that is not part of the production KIS SDK or CLI. The current track is the Candlestick VQ-VAE Tokenizer: converting OHLCV candles into deterministic feature vectors and, later, learned discrete market-state tokens.

## Scope
- Keep research code independent from broker SDK transport code.
- Read already-collected market data from local DuckDB warehouses; do not call broker APIs here.
- Prefer small, testable modules under `research/tokenizers/`.
- Keep ML dependencies optional. Base SDK/CLI users should not need `torch`.

## Out of Scope
Do not add trading signals, order execution, strategy engines, dashboards, or backtesting here unless explicitly requested.
