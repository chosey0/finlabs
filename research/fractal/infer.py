from __future__ import annotations

from typing import Sequence

import numpy as np

from .data import Candle, standardize_features
from .labels import FractalLabelConfig, moving_average
from .model import require_torch


def latest_feature_window(
    candles: Sequence[Candle],
    *,
    max_len: int = 20,
    label_config: FractalLabelConfig | None = None,
    standardize: bool = True,
) -> np.ndarray:
    """Build the live inference feature window from currently available candles."""
    if max_len < 2:
        raise ValueError("max_len must be at least 2")
    if len(candles) < 2:
        raise ValueError("at least two candles are required")

    cfg = label_config or FractalLabelConfig()
    cfg.validate()
    window = tuple(candles)[-max_len:]
    closes = tuple(candle.close for candle in candles)
    short_ma = moving_average(closes, cfg.short_ma)[-len(window) :]
    long_ma = moving_average(closes, cfg.long_ma)[-len(window) :]

    features = np.asarray(
        [
            (
                candle.open,
                candle.high,
                candle.low,
                candle.close,
                short_value if short_value is not None else candle.close,
                long_value if long_value is not None else candle.close,
            )
            for candle, short_value, long_value in zip(window, short_ma, long_ma, strict=True)
        ],
        dtype=np.float32,
    )
    if standardize:
        return standardize_features(features)
    return features


def predict_probabilities(model, features: np.ndarray, *, device: str | None = None) -> tuple[float, ...]:
    """Return softmax probabilities for one feature window."""
    torch, _nn = require_torch()
    resolved_device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = model.to(resolved_device)
    model.eval()

    with torch.no_grad():
        tensor = torch.tensor(features, dtype=torch.float32, device=resolved_device)
        if tensor.ndim == 2:
            tensor = tensor.unsqueeze(0)
        logits = model(tensor)
        probs = torch.softmax(logits, dim=1).flatten().detach().cpu().tolist()

    return tuple(float(prob) for prob in probs)
