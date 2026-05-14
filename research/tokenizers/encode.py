from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from research.tokenizers.data import CandleBar
from research.tokenizers.features import VolumeContext, extract_features_batch
from research.tokenizers.model import require_torch


@dataclass(slots=True)
class Tokenizer:
    model: object
    volume_context: VolumeContext | None = None

    @classmethod
    def load(cls, checkpoint_path: str | Path, *, volume_context: VolumeContext | None = None) -> "Tokenizer":
        torch, _ = require_torch()
        from research.tokenizers.model import VQVAE  # noqa: PLC0415

        if VQVAE is None:
            raise RuntimeError("VQVAE is unavailable")

        checkpoint = torch.load(Path(checkpoint_path), map_location="cpu")
        model = VQVAE(checkpoint["config"])
        model.load_state_dict(checkpoint["state_dict"])
        model.eval()
        return cls(model=model, volume_context=volume_context)

    def encode(self, candles: Iterable[CandleBar]) -> tuple[int, ...]:
        torch, _ = require_torch()
        features = extract_features_batch(tuple(candles), self.volume_context)
        if not features:
            return ()

        inputs = torch.tensor([feature.as_tuple() for feature in features], dtype=torch.float32)
        with torch.no_grad():
            z_e = self.model.encoder(inputs)
            _, indices = self.model.quantizer(z_e)
        return tuple(int(index) for index in indices.cpu().tolist())
