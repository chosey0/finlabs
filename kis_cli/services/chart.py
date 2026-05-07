from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.config.resolver import resolve_profile
from kis_cli.core.chart import OhlcvBar, bar_to_db_values, fetch_ohlcv_history, normalize_period
from kis_cli.core.client import KisClient
from kis_cli.services.auth import get_rest_token
from kis_cli.storage import connect, init_database
from kis_cli.storage.repositories import insert_ohlcv_bars


@dataclass(frozen=True)
class ChartHistoryResult:
    db_path: Path | None
    market: str
    symbol: str
    interval: str
    fetched: int
    stored: int
    bars: list[OhlcvBar]


def collect_ohlcv_history(
    *,
    symbol: str,
    market: str,
    start: str,
    end: str,
    period: str,
    profile: str | None = None,
    config_path: Path | None = None,
    db_path: Path | None = None,
    save: bool = False,
    adjusted: bool = True,
    max_pages: int = 100,
) -> ChartHistoryResult:
    resolved = resolve_profile(profile=profile, config_path=config_path)
    token, _ = get_rest_token(profile=profile, config_path=config_path)
    client = KisClient(profile=resolved, token=token)
    bars = fetch_ohlcv_history(
        client,
        market=market,
        symbol=symbol,
        start=start,
        end=end,
        period=period,
        adjusted=adjusted,
        max_pages=max_pages,
    )
    interval = _period_to_interval(period)
    stored = 0
    initialized_path: Path | None = None
    if save:
        init_result = init_database(db_path)
        initialized_path = init_result.path
        with connect(init_result.path) as connection:
            stored = insert_ohlcv_bars(
                connection,
                (bar_to_db_values(bar) for bar in bars),
            )

    return ChartHistoryResult(
        db_path=initialized_path,
        market=bars[0].market if bars else market.upper(),
        symbol=bars[0].symbol if bars else symbol.upper(),
        interval=interval,
        fetched=len(bars),
        stored=stored,
        bars=bars,
    )


def _period_to_interval(period: str) -> str:
    return {"D": "1d", "W": "1w", "M": "1mo", "Y": "1y"}[normalize_period(period)]
