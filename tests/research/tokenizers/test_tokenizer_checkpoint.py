from pathlib import Path

import pytest

from research.tokenizers.data import CandleBar
from research.tokenizers.encode import Tokenizer
from research.tokenizers.features import build_volume_context, extract_features_batch
from research.tokenizers.model import VQVAEConfig, require_torch
from research.tokenizers.train import TrainConfig, train


def _torch_available() -> bool:
    try:
        require_torch()
    except RuntimeError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _torch_available(), reason="tokenizers optional dependencies are not installed")


def _candles() -> tuple[CandleBar, ...]:
    return tuple(
        CandleBar("NASDAQ", "AAPL", "1d", f"2026-01-{index + 1:02d}", 100 + index, 105 + index, 98 + index, 102 + index, 1_000 + index * 10)
        for index in range(8)
    )


def test_train_writes_weights_only_safe_checkpoint(tmp_path: Path):
    torch, _ = require_torch()
    candles = _candles()
    volume_context = build_volume_context(candles)
    features = extract_features_batch(candles, volume_context)

    result = train(
        features,
        config=TrainConfig(
            output_dir=tmp_path,
            model=VQVAEConfig(codebook_size=4, hidden_dim=8, latent_dim=3),
            epochs=1,
            batch_size=4,
            seed=7,
        ),
    )

    checkpoint = torch.load(result.checkpoint_path, map_location="cpu", weights_only=True)

    assert checkpoint["format_version"] == 2
    assert checkpoint["config"]["codebook_size"] == 4

    tokenizer_a = Tokenizer.load(result.checkpoint_path, volume_context=volume_context)
    tokenizer_b = Tokenizer.load(result.checkpoint_path, volume_context=volume_context)

    assert tokenizer_a.encode(candles) == tokenizer_b.encode(candles)
