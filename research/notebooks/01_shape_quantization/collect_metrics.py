"""collect_metrics.py — aggregate metrics.json from all phase_1b runs into summary.csv.

Usage:
    python collect_metrics.py [--runs-dir RUNS_DIR] [--out OUT]

RUNS_DIR defaults to ./runs (relative to this script).
OUT defaults to ./summary.csv.

Only runs that contain metrics.json are included.
Phase 1A runs (which lack range_bucket / kmeans_shape keys) are skipped with a warning.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path

# ──────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────

def _row_by_split(rows: list[dict], split: str) -> dict:
    for row in rows:
        if row.get("split") == split:
            return row
    return {}


def _safe(value, default=None):
    return value if value is not None else default


def _extract_row(run_dir: Path, metrics: dict, experiment_config: dict) -> dict | None:
    cfg = metrics.get("config", {})
    split_info = metrics.get("split", {})

    # skip Phase 1A runs and deprecated Phase 1B ablation runs (range_scale_z encoder input design)
    if "range_bucket" not in metrics:
        warnings.warn(f"Skipping {run_dir.name}: no range_bucket key (Phase 1A or deprecated Phase 1B ablation)", stacklevel=2)
        return None

    vqvae = metrics.get("vqvae_shape", {})
    rb = metrics.get("range_bucket", {})
    pair = metrics.get("shape_range_pair", {})
    km = metrics.get("kmeans_shape", {})

    vqvae_rows = vqvae.get("rows", [])
    rb_rows = rb.get("rows", [])
    pair_rows = pair.get("rows", [])

    train_shape = _row_by_split(vqvae_rows, "train")
    val_shape = _row_by_split(vqvae_rows, "val")
    test_shape = _row_by_split(vqvae_rows, "test")

    train_rb = _row_by_split(rb_rows, "train")
    val_rb = _row_by_split(rb_rows, "val")
    test_rb = _row_by_split(rb_rows, "test")

    train_pair = _row_by_split(pair_rows, "train")
    val_pair = _row_by_split(pair_rows, "val")
    test_pair = _row_by_split(pair_rows, "test")

    vqvae_val_diff = vqvae.get("val_train_ratio_diff", {})
    vqvae_test_diff = vqvae.get("test_train_ratio_diff", {})
    rb_val_diff = rb.get("val_train_ratio_diff", {})
    rb_test_diff = rb.get("test_train_ratio_diff", {})
    pair_val_diff = pair.get("val_train_ratio_diff", {})
    pair_test_diff = pair.get("test_train_ratio_diff", {})

    km_sv = km.get("shape_val_train_ratio_diff", {})
    km_st = km.get("shape_test_train_ratio_diff", {})
    km_pv = km.get("pair_val_train_ratio_diff", {})
    km_pt = km.get("pair_test_train_ratio_diff", {})

    # split metadata — experiment_config.json is the authoritative source
    train_symbols = _safe(experiment_config.get("train_symbols"), split_info.get("train_symbols"))
    val_symbols = _safe(experiment_config.get("val_symbols"), split_info.get("val_symbols"))
    test_symbols = _safe(experiment_config.get("test_symbols"), split_info.get("test_symbols"))

    return {
        "run_id": run_dir.name,
        "run_dir": str(run_dir.resolve()),
        "phase": _safe(cfg.get("phase"), experiment_config.get("phase")),
        "market": _safe(cfg.get("market"), experiment_config.get("market")),
        "interval": _safe(cfg.get("interval"), experiment_config.get("interval")),
        "codebook_size": _safe(cfg.get("codebook_size"), experiment_config.get("codebook_size")),
        "split_family": _safe(experiment_config.get("split_family")),
        "split_index": _safe(experiment_config.get("split_index")),
        "split_seed": _safe(experiment_config.get("split_seed"), cfg.get("seed")),
        "train_symbols": json.dumps(train_symbols) if train_symbols is not None else "",
        "val_symbols": json.dumps(val_symbols) if val_symbols is not None else "",
        "test_symbols": json.dumps(test_symbols) if test_symbols is not None else "",
        "train_candles": split_info.get("train_candles"),
        "val_candles": split_info.get("val_candles"),
        "test_candles": split_info.get("test_candles"),
        # shape token
        "shape_val_train_l1": vqvae_val_diff.get("l1"),
        "shape_test_train_l1": vqvae_test_diff.get("l1"),
        "shape_val_train_max_diff": vqvae_val_diff.get("max"),
        "shape_test_train_max_diff": vqvae_test_diff.get("max"),
        "shape_train_entropy": train_shape.get("entropy"),
        "shape_val_entropy": val_shape.get("entropy"),
        "shape_test_entropy": test_shape.get("entropy"),
        "shape_train_mean_sc": train_shape.get("mean_semantic_consistency"),
        "shape_val_mean_sc": val_shape.get("mean_semantic_consistency"),
        "shape_test_mean_sc": test_shape.get("mean_semantic_consistency"),
        # range bucket
        "range_val_train_l1": rb_val_diff.get("l1"),
        "range_test_train_l1": rb_test_diff.get("l1"),
        "range_val_train_max_diff": rb_val_diff.get("max"),
        "range_test_train_max_diff": rb_test_diff.get("max"),
        "range_train_entropy": train_rb.get("entropy"),
        "range_val_entropy": val_rb.get("entropy"),
        "range_test_entropy": test_rb.get("entropy"),
        # shape-range pair
        "pair_val_train_l1": pair_val_diff.get("l1"),
        "pair_test_train_l1": pair_test_diff.get("l1"),
        "pair_val_train_max_diff": pair_val_diff.get("max"),
        "pair_test_train_max_diff": pair_test_diff.get("max"),
        "pair_train_entropy": train_pair.get("entropy"),
        "pair_val_entropy": val_pair.get("entropy"),
        "pair_test_entropy": test_pair.get("entropy"),
        # KMeans baseline
        "kmeans_shape_val_train_l1": km_sv.get("l1"),
        "kmeans_shape_test_train_l1": km_st.get("l1"),
        "kmeans_pair_val_train_l1": km_pv.get("l1"),
        "kmeans_pair_test_train_l1": km_pt.get("l1"),
        "kmeans_inertia_per_sample": km.get("inertia_per_sample"),
        "kmeans_shape_mean_sc_train": km.get("mean_semantic_consistency_train"),
        "kmeans_shape_mean_sc_val": km.get("mean_semantic_consistency_val"),
        "kmeans_shape_mean_sc_test": km.get("mean_semantic_consistency_test"),
        "notes": "",
    }


COLUMNS = [
    "run_id", "run_dir", "phase", "market", "interval", "codebook_size",
    "split_family", "split_index", "split_seed",
    "train_symbols", "val_symbols", "test_symbols",
    "train_candles", "val_candles", "test_candles",
    "shape_val_train_l1", "shape_test_train_l1",
    "shape_val_train_max_diff", "shape_test_train_max_diff",
    "shape_train_entropy", "shape_val_entropy", "shape_test_entropy",
    "shape_train_mean_sc", "shape_val_mean_sc", "shape_test_mean_sc",
    "range_val_train_l1", "range_test_train_l1",
    "range_val_train_max_diff", "range_test_train_max_diff",
    "range_train_entropy", "range_val_entropy", "range_test_entropy",
    "pair_val_train_l1", "pair_test_train_l1",
    "pair_val_train_max_diff", "pair_test_train_max_diff",
    "pair_train_entropy", "pair_val_entropy", "pair_test_entropy",
    "kmeans_shape_val_train_l1", "kmeans_shape_test_train_l1",
    "kmeans_pair_val_train_l1", "kmeans_pair_test_train_l1",
    "kmeans_inertia_per_sample",
    "kmeans_shape_mean_sc_train", "kmeans_shape_mean_sc_val", "kmeans_shape_mean_sc_test",
    "notes",
]


def main(runs_dir: Path, out_path: Path) -> None:
    rows: list[dict] = []

    for run_dir in sorted(runs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        metrics_path = run_dir / "metrics.json"
        if not metrics_path.exists():
            continue

        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))

        exp_config_path = run_dir / "experiment_config.json"
        experiment_config: dict = {}
        if exp_config_path.exists():
            experiment_config = json.loads(exp_config_path.read_text(encoding="utf-8"))

        row = _extract_row(run_dir, metrics, experiment_config)
        if row is None:
            continue
        rows.append(row)

    if not rows:
        print("No Phase 1B runs found.", file=sys.stderr)
        sys.exit(1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} run(s) to {out_path}")
    for row in rows:
        print(f"  {row['run_id']:60s}  shape_test_l1={row['shape_test_train_l1']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    script_dir = Path(__file__).parent
    parser.add_argument("--runs-dir", type=Path, default=script_dir / "runs")
    parser.add_argument("--out", type=Path, default=script_dir / "summary.csv")
    args = parser.parse_args()
    main(args.runs_dir, args.out)
