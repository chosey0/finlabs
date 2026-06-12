"""KIS 국내·해외 종목 마스터를 뉴스 데이터베이스에 동기화한다."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

import duckdb
from modules.brokers.kis import SymbolRecord, download_symbol_master, normalize_market

from .db.sql import replace_symbol_snapshots
from .rss.models import SEOUL_TIMEZONE
from .schema.symbol import NewsSymbol


DOMESTIC_SYMBOL_MARKETS = ("KOSPI", "KOSDAQ")
OVERSEAS_SYMBOL_MARKETS = ("NASDAQ", "NYSE", "AMEX")
NEWS_SYMBOL_MARKETS = DOMESTIC_SYMBOL_MARKETS + OVERSEAS_SYMBOL_MARKETS
SymbolMasterDownloader = Callable[..., list[SymbolRecord]]


def update_symbol_masters(
    connection: duckdb.DuckDBPyConnection,
    *,
    markets: Iterable[str] = NEWS_SYMBOL_MARKETS,
    downloader: SymbolMasterDownloader = download_symbol_master,
) -> tuple[int, int]:
    """국내·해외 종목 마스터를 내려받아 뉴스 DB 스냅샷을 교체한다."""

    normalized_markets = _normalize_news_markets(markets)
    downloaded_at = datetime.now(SEOUL_TIMEZONE).isoformat()
    symbols: list[NewsSymbol] = []
    for market in normalized_markets:
        records = downloader(market, downloaded_at=downloaded_at)
        if not records:
            raise ValueError(f"{market} symbol master download returned no rows")
        symbols.extend(_to_news_symbol(record) for record in records)

    stored = replace_symbol_snapshots(connection, symbols)
    return len(symbols), stored


def _normalize_news_markets(markets: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(normalize_market(market) for market in markets))
    if not normalized:
        raise ValueError("at least one symbol market is required")
    unsupported = [market for market in normalized if market not in NEWS_SYMBOL_MARKETS]
    if unsupported:
        allowed = ", ".join(NEWS_SYMBOL_MARKETS)
        raise ValueError(f"news symbol markets must be one of: {allowed}")
    return normalized


def _to_news_symbol(record: SymbolRecord) -> NewsSymbol:
    return NewsSymbol(
        market=record.market,
        symbol=record.symbol,
        standard_code=record.standard_code,
        realtime_symbol=record.realtime_symbol,
        korean_name=record.korean_name,
        english_name=record.english_name,
        security_type=record.security_type,
        currency=record.currency,
        exchange_id=record.exchange_id,
        exchange_code=record.exchange_code,
        exchange_name=record.exchange_name,
        country_code=record.country_code,
        listed_date=record.listed_date,
        base_price=record.base_price,
        lot_size=record.lot_size,
        raw_source=record.raw_source,
        raw=record.raw,
        downloaded_at=record.downloaded_at,
    )
