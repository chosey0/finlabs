from __future__ import annotations

from pathlib import Path

from kis_cli.config.resolver import resolve_profile
from kis_cli.core.client import KisClient
from kis_cli.core.price import CurrentPrice, inquire_current_price
from kis_cli.services.auth import get_rest_token


def get_current_price(
    *,
    symbol: str,
    market: str,
    profile: str | None = None,
    config_path: Path | None = None,
) -> CurrentPrice:
    resolved = resolve_profile(profile=profile, config_path=config_path)
    token, _ = get_rest_token(profile=profile, config_path=config_path)
    client = KisClient(profile=resolved, token=token)
    return inquire_current_price(client, market=market, symbol=symbol)
