"""뉴스 전용 종목 마스터 동기화의 회귀 동작을 검증한다."""

from __future__ import annotations

import pytest
from modules.brokers.kis import SymbolRecord

from modules.news.symbols import update_symbol_masters


def _record(market: str, symbol: str, name: str) -> SymbolRecord:
    return SymbolRecord(
        market=market,
        symbol=symbol,
        standard_code=f"KR{symbol}",
        realtime_symbol=symbol,
        korean_name=name,
        security_type="STOCK",
        exchange_id=market,
        exchange_code="KRX",
        exchange_name="Korea Exchange",
        listed_date="20000101",
        base_price=1000,
        lot_size=1,
        raw_source=f"{market.lower()}_code.mst",
        raw={"short_code": symbol, "korean_name": name},
    )


def test_update_symbol_masters_splits_domestic_and_overseas_markets_atomically(
    news_connection,
):
    connection = news_connection
    calls: list[tuple[str, str]] = []

    def download(market: str, *, downloaded_at: str):
        calls.append((market, downloaded_at))
        records = {
            "KOSPI": [_record("KOSPI", "005930", "삼성전자")],
            "KOSDAQ": [_record("KOSDAQ", "035720", "카카오")],
            "NASDAQ": [_record("NASDAQ", "AAPL", "애플")],
            "NYSE": [_record("NYSE", "IBM", "IBM")],
            "AMEX": [_record("AMEX", "SPY", "SPDR S&P 500 ETF")],
        }
        return [record.with_downloaded_at(downloaded_at) for record in records[market]]

    downloaded, stored = update_symbol_masters(connection, downloader=download)

    assert (downloaded, stored) == (5, 5)
    assert [market for market, _ in calls] == [
        "KOSPI",
        "KOSDAQ",
        "NASDAQ",
        "NYSE",
        "AMEX",
    ]
    assert len({downloaded_at for _, downloaded_at in calls}) == 1
    assert connection.execute(
        """SELECT market, symbol, korean_name, raw->>'korean_name'
        FROM domestic_symbols ORDER BY market"""
    ).fetchall() == [
        ("KOSDAQ", "035720", "카카오", "카카오"),
        ("KOSPI", "005930", "삼성전자", "삼성전자"),
    ]
    assert connection.execute(
        "SELECT market, symbol FROM overseas_symbols ORDER BY market"
    ).fetchall() == [
        ("AMEX", "SPY"),
        ("NASDAQ", "AAPL"),
        ("NYSE", "IBM"),
    ]


def test_update_symbol_masters_replaces_removed_symbols_for_one_market(
    news_connection,
):
    connection = news_connection
    snapshots = iter(
        [
            [
                _record("KOSPI", "005930", "삼성전자"),
                _record("KOSPI", "000660", "SK하이닉스"),
            ],
            [_record("KOSPI", "005930", "삼성전자")],
        ]
    )

    def download(market: str, *, downloaded_at: str):
        assert market == "KOSPI"
        return [record.with_downloaded_at(downloaded_at) for record in next(snapshots)]

    update_symbol_masters(connection, markets=("KOSPI",), downloader=download)
    update_symbol_masters(connection, markets=("KOSPI",), downloader=download)

    assert connection.execute(
        "SELECT symbol FROM domestic_symbols WHERE market = 'KOSPI'"
    ).fetchall() == [("005930",)]


def test_empty_symbol_download_preserves_existing_snapshot(news_connection):
    connection = news_connection

    def initial_download(market: str, *, downloaded_at: str):
        return [_record(market, "005930", "삼성전자").with_downloaded_at(downloaded_at)]

    update_symbol_masters(
        connection,
        markets=("KOSPI",),
        downloader=initial_download,
    )

    with pytest.raises(ValueError, match="returned no rows"):
        update_symbol_masters(
            connection,
            markets=("KOSPI",),
            downloader=lambda market, *, downloaded_at: [],
        )

    assert connection.execute(
        "SELECT market, symbol FROM domestic_symbols"
    ).fetchall() == [("KOSPI", "005930")]


def test_news_symbol_update_rejects_unsupported_markets(news_connection):
    connection = news_connection

    with pytest.raises(ValueError, match="KOSPI, KOSDAQ, NASDAQ, NYSE, AMEX"):
        update_symbol_masters(
            connection,
            markets=("HKEX",),
            downloader=lambda market, *, downloaded_at: [],
        )


def test_duplicate_symbols_are_deduplicated_keeping_last(news_connection):
    """API가 동일 코드를 두 번 반환해도 나중 항목을 저장하고 오류를 내지 않는다."""

    connection = news_connection

    def duplicate_download(market: str, *, downloaded_at: str):
        return [
            _record(market, "005930", "삼성전자구버전").with_downloaded_at(
                downloaded_at
            ),
            _record(market, "005930", "삼성전자최신").with_downloaded_at(downloaded_at),
        ]

    downloaded, stored = update_symbol_masters(
        connection,
        markets=("KOSPI",),
        downloader=duplicate_download,
    )

    rows = connection.execute(
        "SELECT symbol, korean_name FROM domestic_symbols WHERE market = 'KOSPI'"
    ).fetchall()
    assert rows == [("005930", "삼성전자최신")]
    assert stored == 1
