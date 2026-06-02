from __future__ import annotations

from dataclasses import dataclass

try:  # pragma: no cover - exercised when optional dependency is installed
    import torch
    from torch import nn
except ImportError:  # pragma: no cover - default lightweight environment
    torch = None
    nn = None


@dataclass(frozen=True, slots=True)
class CNN1DConfig:
    input_size: int = 6
    output_size: int = 3
    pooled_steps: int = 8

    def validate(self) -> None:
        if self.input_size <= 0:
            raise ValueError("input_size must be positive")
        if self.output_size <= 1:
            raise ValueError("output_size must be greater than 1")
        if self.pooled_steps <= 0:
            raise ValueError("pooled_steps must be positive")


def require_torch():
    if torch is None or nn is None:
        raise RuntimeError("research.fractal requires torch for model and training code.")
    return torch, nn


if nn is not None:  # pragma: no cover - optional ML path

    class CNN1D(nn.Module):
        """Small 1D CNN used by the original Fractal prototype.

        Input shape is ``batch x steps x features``. Internally the tensor is
        transposed to ``batch x features x steps`` for ``Conv1d``.
        """

        def __init__(self, config: CNN1DConfig | None = None) -> None:
            super().__init__()
            self.config = config or CNN1DConfig()
            self.config.validate()

            input_size = self.config.input_size
            pooled_steps = self.config.pooled_steps
            self.conv1 = nn.Conv1d(input_size, input_size * 2, kernel_size=1, padding=0)
            self.conv2 = nn.Conv1d(input_size * 2, input_size * 4, kernel_size=1, padding=0)
            self.conv3 = nn.Conv1d(input_size * 4, input_size * 8, kernel_size=1, padding=0)
            self.pool = nn.AdaptiveAvgPool1d(pooled_steps)
            self.fc1 = nn.Linear(input_size * 8 * pooled_steps, input_size * 8 * 4)
            self.relu = nn.ReLU()
            self.fc2 = nn.Linear(input_size * 8 * 4, self.config.output_size)

        def forward(self, inputs):
            x = inputs.transpose(1, 2)
            x = self.pool(torch.relu(self.conv1(x)))
            x = self.pool(torch.relu(self.conv2(x)))
            x = self.pool(torch.relu(self.conv3(x)))
            x = self.fc1(x.flatten(1))
            return self.fc2(self.relu(x))

else:
    CNN1D = None
