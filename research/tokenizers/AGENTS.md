<!-- Parent: ../AGENTS.md, ../research/AGENTS.md -->

# research/tokenizers

## Purpose
Candlestick tokenizer research package. It starts with deterministic OHLCV feature extraction and DuckDB loading, then layers optional VQ-VAE training and encoding on top.

## Rules
- Feature extraction must be deterministic for the same candle and volume context.
- DuckDB loading must preserve timestamp order and use explicit market/symbol/interval filters.
- `torch` code must remain optional and fail with a clear message when the optional dependency is missing.
- Tests must use synthetic data and `tmp_path`; never call real broker APIs.
- Keep public dataclasses typed and simple so research notebooks/scripts can consume them.
