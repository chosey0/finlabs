"""Download the KIS domestic symbol master straight into PostgreSQL.

This skips the DuckDB warehouse entirely: it pulls the KIS-published master file
for each domestic market, maps it to the news-intelligence ``domestic_symbols``
schema, and atomically replaces the catalog in PostgreSQL. The KIS master files
are public downloads, so only the PostgreSQL connection string is required — no
Kiwoom or KIS credentials.

Usage:
    INTELLIGENCE_DATABASE_URL=postgresql://... \
        uv run --group postgres python -m scripts.load_kis_symbols_to_supabase \
        [--markets KOSPI KOSDAQ] [--dsn postgresql://...]
"""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from modules.brokers.kis import (
    SymbolRecord,
    download_symbol_master,
    normalize_market,
)
from modules.storage.news_intelligence.database import resolve_dsn
from scripts.seed_intelligence_catalog import _COLUMNS, seed

DOMESTIC_MARKETS = ("KOSPI", "KOSDAQ")
_KST = ZoneInfo("Asia/Seoul")


def _normalize_markets(markets: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(normalize_market(market) for market in markets))
    if not normalized:
        raise SystemExit("at least one market is required")
    unsupported = [market for market in normalized if market not in DOMESTIC_MARKETS]
    if unsupported:
        raise SystemExit(
            f"only domestic markets are supported: {', '.join(DOMESTIC_MARKETS)}"
        )
    return normalized


def collect_rows(
    markets: Iterable[str],
    *,
    downloader=download_symbol_master,
    timeout_seconds: float = 30.0,
    on_market_downloaded=None,
) -> list[tuple[object, ...]]:
    """Download each market's master and flatten it to domestic_symbols rows."""

    downloaded_at = datetime.now(_KST).isoformat()
    rows: list[tuple[object, ...]] = []
    for market in _normalize_markets(markets):
        records: list[SymbolRecord] = downloader(
            market, downloaded_at=downloaded_at, timeout_seconds=timeout_seconds
        )
        if not records:
            raise SystemExit(f"{market} symbol master download returned no rows")
        rows.extend(tuple(getattr(record, column) for column in _COLUMNS) for record in records)
        if on_market_downloaded is not None:
            on_market_downloaded(market, len(records))
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--markets",
        nargs="+",
        default=list(DOMESTIC_MARKETS),
        help="Domestic markets to load (default: KOSPI KOSDAQ).",
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help="PostgreSQL connection string (default: INTELLIGENCE_DATABASE_URL).",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-market download timeout in seconds (default: 30).",
    )
    args = parser.parse_args()

    def _announce(market: str, count: int) -> None:
        print(f"downloaded {market}: {count} symbols")

    rows = collect_rows(
        args.markets,
        timeout_seconds=args.timeout,
        on_market_downloaded=_announce,
    )
    count = seed(resolve_dsn(args.dsn), rows)
    print(f"loaded {count} domestic symbols into PostgreSQL")


if __name__ == "__main__":
    main()
