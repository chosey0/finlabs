<!-- Parent: ../AGENTS.md -->

# research

## Purpose
`research/` contains experimental market-representation work that is not part of the production KIS SDK or CLI. The current track is split into three research phases: Shape Quantization, Sequential Dynamics, and Market State Modeling. `research/tokenizers/` currently implements the Phase 1 tokenizer foundation and Phase 2 sequence metric primitives.

## Scope
- Keep research code independent from broker SDK transport code.
- Read already-collected market data from local DuckDB warehouses; do not call broker APIs here.
- Prefer small, testable modules under `research/tokenizers/`.
- Treat Phase 1 tokens as `shape tokens` until Phase 2/3 evidence supports stronger market-state claims.
- Keep ML dependencies optional. Base SDK/CLI users should not need `torch`.

## Out of Scope
Do not add trading signals, order execution, strategy engines, dashboards, or backtesting here unless explicitly requested.
