from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from research.tokenizers.data import CandleBar
from research.tokenizers.features import VolumeContext, extract_features_batch
from research.tokenizers.model import VQVAEConfig, require_torch


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

        path = Path(checkpoint_path)
        try:
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        except Exception as exc:  # noqa: BLE001 - normalize PyTorch version-specific load errors
            raise RuntimeError(
                "Tokenizer checkpoint를 안전하게 load하지 못했습니다. "
                "PyTorch 2.6+에서는 pickled config 객체가 포함된 legacy checkpoint가 차단됩니다. "
                "신뢰 가능한 직접 생성 checkpoint라면 train cell을 다시 실행해 format_version=2 checkpoint를 재생성하세요."
            ) from exc

        model_config = _load_model_config(checkpoint.get("config"))
        model = VQVAE(model_config)
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
            _z_q_st, _z_q, indices = self.model.quantizer(z_e)
        return tuple(int(index) for index in indices.cpu().tolist())


def _load_model_config(raw_config: object) -> VQVAEConfig:
    if isinstance(raw_config, VQVAEConfig):
        return raw_config
    if isinstance(raw_config, dict):
        return VQVAEConfig(**raw_config)
    raise RuntimeError("checkpoint config is missing or invalid")
