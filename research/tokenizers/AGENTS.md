<!-- Parent: ../AGENTS.md, ../research/AGENTS.md -->

# research/tokenizers

## Purpose
Candlestick tokenizer research package for Phase 1 Shape Quantization. It starts with deterministic OHLCV feature extraction and DuckDB loading, then layers optional VQ-VAE training and encoding on top. Phase 2 Sequential Dynamics belongs in sequence metric helpers; Phase 3 Market State Modeling should not be implemented here until explicitly specified.

## Rules
- Feature extraction must be deterministic for the same candle and volume context.
- Call learned outputs `shape tokens` in Phase 1; reserve `market state` wording for Phase 3 evidence.
- DuckDB loading must preserve timestamp order and use explicit market/symbol/interval filters.
- `torch` code must remain optional and fail with a clear message when the optional dependency is missing.
- Tests must use synthetic data and `tmp_path`; never call real broker APIs.
- Keep public dataclasses typed and simple so research notebooks/scripts can consume them.
- New Phase 1 metrics go in `shape_metrics.py`; Phase 2 transition metrics go in `sequence_metrics.py`.
