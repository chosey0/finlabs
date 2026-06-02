from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from .data import FractalSample, pad_feature_batch
from .model import CNN1DConfig, require_torch


@dataclass(frozen=True, slots=True)
class TrainConfig:
    batch_size: int = 128
    epochs: int = 10
    learning_rate: float = 0.01
    class_balanced: bool = True
    device: str | None = None

    def validate(self) -> None:
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if self.epochs <= 0:
            raise ValueError("epochs must be positive")
        if self.learning_rate <= 0:
            raise ValueError("learning_rate must be positive")


def train_cnn1d(
    samples: Sequence[FractalSample],
    *,
    model_config: CNN1DConfig | None = None,
    train_config: TrainConfig | None = None,
):
    """Train CNN1D from in-memory fractal samples."""
    torch, nn = require_torch()
    from torch.utils.data import DataLoader, TensorDataset

    from .model import CNN1D

    if CNN1D is None:
        raise RuntimeError("CNN1D is unavailable because torch is not installed")
    if not samples:
        raise ValueError("samples must not be empty")

    cfg = train_config or TrainConfig()
    cfg.validate()
    model_cfg = model_config or CNN1DConfig()
    model_cfg.validate()

    data, labels, _lengths = pad_feature_batch(samples)
    x_tensor = torch.tensor(data, dtype=torch.float32)
    y_tensor = torch.tensor(labels, dtype=torch.long)
    dataset = TensorDataset(x_tensor, y_tensor)

    sampler = None
    if cfg.class_balanced:
        sampler = _weighted_sampler(labels, torch=torch)

    loader = DataLoader(
        dataset,
        batch_size=cfg.batch_size,
        shuffle=sampler is None,
        sampler=sampler,
    )

    device = torch.device(cfg.device or ("cuda" if torch.cuda.is_available() else "cpu"))
    model = CNN1D(model_cfg).to(device)
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=cfg.learning_rate)

    history: list[dict[str, float]] = []
    model.train()
    for _epoch in range(cfg.epochs):
        total_loss = 0.0
        total_correct = 0
        total_count = 0
        for batch_x, batch_y in loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            logits = model(batch_x)
            loss = criterion(logits, batch_y)
            loss.backward()
            optimizer.step()

            total_loss += float(loss.detach().cpu()) * int(batch_y.shape[0])
            total_correct += int((logits.argmax(dim=1) == batch_y).sum().detach().cpu())
            total_count += int(batch_y.shape[0])

        history.append(
            {
                "loss": total_loss / max(total_count, 1),
                "accuracy": total_correct / max(total_count, 1),
            }
        )

    return model, history


def _weighted_sampler(labels: np.ndarray, *, torch):
    counts = Counter(int(label) for label in labels)
    sample_weights = np.asarray(
        [len(labels) / counts[int(label)] for label in labels],
        dtype=np.float64,
    )
    sample_weights = sample_weights / sample_weights.sum()
    return torch.utils.data.WeightedRandomSampler(
        sample_weights,
        num_samples=len(sample_weights),
        replacement=True,
    )
