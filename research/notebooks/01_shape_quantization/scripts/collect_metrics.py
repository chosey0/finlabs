"""collect_metrics.py — aggregate metrics.json from all phase_1b runs into summary.csv.

Usage:
    python scripts/collect_metrics.py [--runs-dir RUNS_DIR] [--out OUT]

RUNS_DIR defaults to ../runs (relative to this script).
OUT defaults to ../summaries/summary.csv.

RUNS_DIR is scanned recursively, so phase-grouped layouts such as
runs/phase_1b/<run>/ and runs/deprecated/<run>/ are all picked up.

Only runs that contain metrics.json are included.
Phase 1A runs and deprecated Phase 1B ablation runs (which lack the
range_bucket key) are skipped with a warning.

In addition to the combined summary.csv, one CSV per split_family is written
next to it (e.g. summary_random.csv, summary_manual_stress.csv) so that
protocol section 10 — separate aggregation per split family — is satisfied.

When runs record ``min_volume`` in experiment_config.json, additional
volume-filter-specific CSVs are written as well (e.g. summary_vge2.csv and
summary_random_vge2.csv).
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
        "min_volume": _safe(experiment_config.get("min_volume"), cfg.get("min_volume")),
        "volume_filter": _safe(experiment_config.get("volume_filter"), cfg.get("volume_filter")),
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
    "min_volume", "volume_filter",
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


def _write_csv(out_path: Path, rows: list[dict]) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(runs_dir: Path, out_path: Path) -> None:
    rows: list[dict] = []

    # rglob is recursive — handles flat runs/, phase-grouped runs/phase_1b/<run>/,
    # and runs/deprecated/<run>/ uniformly. Deprecated and Phase 1A runs still
    # get filtered out by the range_bucket check inside _extract_row.
    for metrics_path in sorted(runs_dir.rglob("metrics.json")):
        run_dir = metrics_path.parent

        # deprecated/ is an explicit aggregation boundary. Skip anything under it
        # even if it is a structurally valid Phase 1B run (has range_bucket).
        if "deprecated" in run_dir.relative_to(runs_dir).parts:
            warnings.warn(f"Skipping {run_dir.name}: under deprecated/", stacklevel=2)
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

    _write_csv(out_path, rows)
    print(f"Wrote {len(rows)} run(s) to {out_path}")

    # one CSV per split_family — protocol section 10 forbids mixing
    # manual_stress with random / vol_* in a single aggregate.
    by_family: dict[str, list[dict]] = {}
    for row in rows:
        family = row.get("split_family") or "unknown"
        by_family.setdefault(family, []).append(row)

    for family, family_rows in sorted(by_family.items()):
        family_path = out_path.with_name(f"{out_path.stem}_{family}{out_path.suffix}")
        _write_csv(family_path, family_rows)
        print(f"Wrote {len(family_rows)} run(s) to {family_path}")

    # Also write filter-specific summaries so volume-filtered reruns can be
    # reviewed without mixing them with earlier unfiltered experiments.
    by_volume: dict[str, list[dict]] = {}
    by_family_volume: dict[tuple[str, str], list[dict]] = {}
    for row in rows:
        min_volume = row.get("min_volume")
        if min_volume in (None, ""):
            continue
        volume_key = f"vge{min_volume}"
        family = row.get("split_family") or "unknown"
        by_volume.setdefault(volume_key, []).append(row)
        by_family_volume.setdefault((family, volume_key), []).append(row)

    for volume_key, volume_rows in sorted(by_volume.items()):
        volume_path = out_path.with_name(f"{out_path.stem}_{volume_key}{out_path.suffix}")
        _write_csv(volume_path, volume_rows)
        print(f"Wrote {len(volume_rows)} run(s) to {volume_path}")

    for (family, volume_key), family_volume_rows in sorted(by_family_volume.items()):
        family_volume_path = out_path.with_name(
            f"{out_path.stem}_{family}_{volume_key}{out_path.suffix}"
        )
        _write_csv(family_volume_path, family_volume_rows)
        print(f"Wrote {len(family_volume_rows)} run(s) to {family_volume_path}")

    for row in rows:
        family = row.get("split_family")
        print(f"  {row['run_id']:60s}  [{family}]  shape_test_l1={row['shape_test_train_l1']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    script_dir = Path(__file__).resolve().parent
    phase_dir = script_dir.parent
    parser.add_argument("--runs-dir", type=Path, default=phase_dir / "runs")
    parser.add_argument("--out", type=Path, default=phase_dir / "summaries" / "summary.csv")
    args = parser.parse_args()
    main(args.runs_dir, args.out)
