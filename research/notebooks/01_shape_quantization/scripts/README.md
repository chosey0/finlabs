## Background

finlabs is a research project that quantizes financial time-series (OHLCV candles)
into discrete tokens. Phase 1B experiments with the following representation:

  shape_token  = discrete token learned by VQ-VAE on 4D price-shape features
  range_bucket = volatility context computed by a train-quantile bucketizer
  final rep    = (shape_token, range_bucket)

So far, symbol splits have been changed manually inside a notebook, yielding only
3-4 runs (all manual_stress family). The goal now is to automate this into a
repeatable validation protocol that can run random, volatility-stratified, and
volatility-held-out split families at scale.

---

## Files to Read Before Starting

Read every file below before writing code. The notebook already contains the full
VQ-VAE training, RangeBucketizer, metric computation, and figure generation logic.
Extract it; do not re-implement it.

1. research/notebooks/01_shape_quantization/02_phase_1b_shape_token_plus_range_bucket.ipynb
   The authoritative source for all training and evaluation logic.

2. research/notebooks/01_shape_quantization/03_symbol_split_protocol.md
   Defines the four split families (section 4), required metrics (section 5),
   run naming convention (section 7), aggregation schema (section 8), and
   Phase 2 entry criteria (section 11).

3. research/notebooks/01_shape_quantization/scripts/collect_metrics.py
   Aggregates each run's metrics.json into summaries/summary.csv.
   Do NOT modify this file. Existing runs must continue to aggregate correctly.

4. research/notebooks/01_shape_quantization/runs/phase_1b_shape_token_range_bucket_NASDAQ_1m_k12/metrics.json
   Canonical example of the metrics.json schema that collect_metrics.py expects.

5. research/notebooks/01_shape_quantization/runs/phase_1b_shape_token_range_bucket_NASDAQ_1m_k12/experiment_config.json
   Canonical example of the experiment_config.json schema.

---

## What to Build

File location:

    research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py

Purpose: a CLI runner that executes Phase 1B (shape_token + range_bucket)
experiments across multiple symbol splits automatically. It must support all
four split families defined in 03_symbol_split_protocol.md:

  random       - random train/val/test symbol assignment from the universe
  vol_strat    - stratified sampling so each volatility tertile is represented
                 in train/val/test
  vol_holdout  - entire high-volatility group withheld for val/test
  stress       - researcher-specified fixed split (passed via --train-symbols,
                 --val-symbols, --test-symbols)

CLI examples (each backslash continues the same shell command):

    uv run python research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
      --split-family random \
      --n-runs 5 \
      --seed-start 0

    uv run python research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
      --split-family vol_strat \
      --n-runs 3 \
      --seed-start 0

    uv run python research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
      --split-family vol_holdout \
      --n-runs 2 \
      --seed-start 0

    uv run python research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
      --split-family stress \
      --n-runs 1 \
      --seed-start 0 \
      --train-symbols AAPL MSFT NVDA TSLA AMZN META GOOGL \
      --val-symbols AMD \
      --test-symbols INTC RKLB

    uv run python research/notebooks/01_shape_quantization/scripts/run_repeated_splits.py \
      --split-family random \
      --n-runs 5 \
      --seed-start 0 \
      --dry-run

Per-run output: each run produces a directory under runs/ following the naming
convention from 03_symbol_split_protocol.md section 7. The template is:

    phase_1b_shape_token_range_bucket_{MARKET}_{INTERVAL}_k{K}_{FAMILY}_{INDEX:02d}/
      experiment_config.json
      metrics.json
      figures/
        01_shape_token_ratio_histogram.png
        02_range_bucket_ratio_histogram.png
        03_shape_range_pair_heatmap.png
        04_per_symbol_range_bucket_heatmap.png
        05_per_symbol_shape_token_heatmap.png
        06_vqvae_vs_kmeans_shape_histogram.png

Concrete example directory names:

    phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_random_00
    phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_vol_strat_00
    phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_vol_holdout_00
    phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_stress_00

Per-run console summary: after each completed run, print a concise summary:

    [run_id]
    train symbols : AAPL MSFT NVDA ...
    val symbols   : AMD
    test symbols  : INTC RKLB
    candles       : train=84000  val=12000  test=24000
    shape_test_l1 : 0.0982
    range_test_l1 : 0.4120
    pair_test_l1  : 0.4873
    dead tokens   : 0 / 12

After all runs complete: call collect_metrics.py via subprocess to regenerate
summaries/summary.csv automatically.

---

## Critical Constraints

No data leakage (strictly enforced):

  - VQ-VAE must be trained on train candles only.
  - RangeBucketizer quantile thresholds must be fit on train candles only.
  - val and test candles are transformed using train-derived statistics only.
  - Held-out symbol candles must never appear in any fit step.

Volatility stratification (vol_strat and vol_holdout families):

  - Compute each symbol's volatility profile as median log_range_pct over ALL
    available candles for that symbol (after max_candles_per_symbol cap).
  - Divide symbols into low/medium/high tertiles from these summary statistics.
    This is a split-assignment step, not a per-split computation.
  - Do NOT recompute volatility using only train candles after the split is
    decided - that would create a circular dependency.
  - vol_strat: sample train/val/test symbols from each tertile proportionally.
  - vol_holdout: assign high-volatility symbols entirely to val/test.
  - Record tertile boundaries and per-symbol group membership inside
    experiment_config.json.
  - See 03_symbol_split_protocol.md section 4.2 for the detailed rationale.

experiment_config.json required fields (collect_metrics.py depends on these):

    phase, market, interval, codebook_size,
    split_family, split_index, split_seed,
    train_symbols, val_symbols, test_symbols

split_family naming:

  - For newly generated stress runs, use split_family: "stress".
  - Existing manually-created runs may continue to use
    split_family: "manual_stress".
  - Do not rewrite any existing experiment_config.json files.

Existing runs must not be broken:

  The existing manually-created Phase 1B runs, including directories whose names
  do not follow the new repeated-split naming convention - namely
  phase_1b_shape_token_range_bucket_NASDAQ_1m_k12,
  phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_a,
  phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_b,
  phase_1b_shape_token_range_bucket_NASDAQ_1m_k12_c -
  must continue to aggregate correctly through collect_metrics.py.

Do not overwrite existing run directories:

  If the target run directory already exists, fail fast with a clear error
  message. Do not silently overwrite existing artifacts. A future --overwrite
  flag may be added later, but it is out of scope for this task.

Do not modify collect_metrics.py.

---

## --dry-run output

When --dry-run is passed, print the following and create no directories:

  - Symbol universe after min-candle filtering
  - Volatility tertile boundaries (for vol_strat and vol_holdout)
  - Low / medium / high volatility group membership
  - Planned train / val / test symbols for each of the N runs

---

## Default Configuration

Used unless overridden by CLI flags:

    market                 = "NASDAQ"
    interval               = "1m"
    codebook_size          = 12
    max_candles_per_symbol = 12000
    min_candles_per_symbol = 500
    train_symbol_ratio     = 0.70
    val_symbol_ratio       = 0.15
    # remainder goes to test

    symbol_universe = [
        "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
        "AMD",  "INTC", "RKLB", "AVGO", "NFLX", "PLTR",
        "MU",   "SOXX", "QQQ", "QCOM", "MRVL",
    ]

    runs_dir = Path(__file__).parent / "runs"

---

## Scope Constraints

  - Extract and refactor logic from the existing notebook; do not re-implement
    VQ-VAE, RangeBucketizer, or metric computation from scratch.
  - Use type hints and argparse. Keep abstraction flat - no unnecessary class
    hierarchies or plugin systems.
  - Do not alter the existing runs/ directory structure or any existing run's
    artifacts.
  - Error handling must cover:
      * symbol not found in DuckDB -> skip with a warning
      * fewer candles than min_candles_per_symbol -> skip with a warning
      * failed VQ-VAE convergence (dead token ratio > 0.5) -> warn but still
        save artifacts so the run is not silently lost