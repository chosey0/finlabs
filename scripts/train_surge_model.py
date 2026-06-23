"""Train and evaluate the surge-ranking model from an exported dataset snapshot.

Usage:
    uv run python -m scripts.train_surge_model <dataset.json> [--k 10] \
        [--out-of-time-fraction 0.2] [--model ridge|lightgbm] [--text-dim 64]

The dataset file is a frozen snapshot export (``{"manifest", "members", ...}``).
Prints the evaluation report (out-of-time ranking quality, baselines, slices) as
JSON so it can be captured or diffed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from modules.news.intelligence.modeling.dataset import load_surge_samples
from modules.news.intelligence.modeling.features import HashingTextEmbedder
from modules.news.intelligence.modeling.model import LightGbmRegressor, RidgeRegressor
from modules.news.intelligence.modeling.pipeline import train_and_evaluate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the surge-ranking model")
    parser.add_argument("dataset", type=Path, help="Path to the snapshot JSON export")
    parser.add_argument("--k", type=int, default=10, help="Ranking cutoff k")
    parser.add_argument("--out-of-time-fraction", type=float, default=0.2)
    parser.add_argument("--model", choices=("ridge", "lightgbm"), default="ridge")
    parser.add_argument("--text-dim", type=int, default=64)
    args = parser.parse_args(argv)

    snapshot = json.loads(args.dataset.read_text(encoding="utf-8"))
    rows = load_surge_samples(snapshot)
    if not rows:
        print("dataset has no members", file=sys.stderr)
        return 1

    embedder = HashingTextEmbedder(dimension=args.text_dim)
    model_factory = RidgeRegressor if args.model == "ridge" else LightGbmRegressor
    report = train_and_evaluate(
        rows,
        embedder=embedder,
        model_factory=model_factory,
        k=args.k,
        out_of_time_fraction=args.out_of_time_fraction,
    )
    print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
