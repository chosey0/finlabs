from __future__ import annotations

from pathlib import Path

from kis_cli.core.price import CurrentPrice, inquire_current_price
from kis_cli.services.auth import call_with_token_refresh_retry


def get_current_price(
    *,
    symbol: str,
    market: str,
    profile: str | None = None,
    config_path: Path | None = None,
) -> CurrentPrice:
    return call_with_token_refresh_retry(
        lambda client: inquire_current_price(client, market=market, symbol=symbol),
        profile=profile,
        config_path=config_path,
    )
