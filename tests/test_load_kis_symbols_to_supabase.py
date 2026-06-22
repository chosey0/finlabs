from modules.brokers.kis import SymbolRecord
from scripts.load_kis_symbols_to_supabase import SYMBOL_MARKETS, collect_rows


def test_collect_rows_downloads_domestic_and_us_markets():
    downloaded: list[tuple[str, str, float]] = []

    def download(market: str, *, downloaded_at: str, timeout_seconds: float):
        downloaded.append((market, downloaded_at, timeout_seconds))
        return [
            SymbolRecord(
                market=market,
                symbol=f"{market}-SYMBOL",
                korean_name=f"{market} name",
                downloaded_at=downloaded_at,
            )
        ]

    rows = collect_rows(SYMBOL_MARKETS, downloader=download, timeout_seconds=12.5)

    assert [market for market, _, _ in downloaded] == list(SYMBOL_MARKETS)
    assert {row[0] for row in rows} == set(SYMBOL_MARKETS)
    assert all(timeout == 12.5 for _, _, timeout in downloaded)
    assert len({downloaded_at for _, downloaded_at, _ in downloaded}) == 1


def test_collect_rows_normalizes_and_deduplicates_markets():
    downloaded: list[str] = []

    def download(market: str, **_kwargs):
        downloaded.append(market)
        return [SymbolRecord(market=market, symbol="AAPL")]

    collect_rows(("nasdaq", " NASDAQ ", "nyse"), downloader=download)

    assert downloaded == ["NASDAQ", "NYSE"]
