import pytest

from research.tokenizers.model import VQVAEConfig, require_torch


def _torch_available() -> bool:
    try:
        require_torch()
    except RuntimeError:
        return False
    return True


pytestmark = pytest.mark.skipif(not _torch_available(), reason="tokenizers optional dependencies are not installed")


def test_vqvae_forward_returns_raw_and_straight_through_quantized_tensors():
    torch, _ = require_torch()
    from research.tokenizers.model import VQVAE

    model = VQVAE(VQVAEConfig(input_dim=7, hidden_dim=8, latent_dim=3, codebook_size=4))
    inputs = torch.randn(5, 7)

    reconstruction, z_e, z_q_st, z_q, indices = model(inputs)

    assert reconstruction.shape == inputs.shape
    assert z_e.shape == (5, 3)
    assert z_q_st.shape == (5, 3)
    assert z_q.shape == (5, 3)
    assert indices.shape == (5,)
    assert z_q.requires_grad
    assert z_q_st.requires_grad


def test_codebook_loss_updates_embedding_gradients():
    torch, _ = require_torch()
    from research.tokenizers.model import VQVAE

    model = VQVAE(VQVAEConfig(input_dim=7, hidden_dim=8, latent_dim=3, codebook_size=4))
    inputs = torch.randn(5, 7)

    reconstruction, z_e, _z_q_st, z_q, _indices = model(inputs)
    reconstruction_loss = torch.mean((reconstruction - inputs) ** 2)
    codebook_loss = torch.mean((z_q - z_e.detach()) ** 2)
    commitment_loss = torch.mean((z_e - z_q.detach()) ** 2)
    loss = reconstruction_loss + codebook_loss + model.config.commitment_cost * commitment_loss
    loss.backward()

    gradient = model.quantizer.embedding.weight.grad
    assert gradient is not None
    assert torch.count_nonzero(gradient).item() > 0
