from __future__ import annotations

import zipfile
from io import BytesIO

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.core.symbol_master import (
    KOSPI_PART2_COLUMNS,
    KOSPI_WIDTHS,
    SymbolRecord,
    parse_symbol_master,
    record_to_db_values,
)
from kis_cli.services.symbols import SymbolDownloadResult
from kis_cli.storage import connect
from kis_cli.storage.app_repositories import list_api_logs, list_ingest_runs

runner = CliRunner()


def test_parse_kospi_master_normalizes_fixed_width_record() -> None:
    part2_values = {column: "" for column in KOSPI_PART2_COLUMNS}
    part2_values.update(
        {
            "group_code": "ST",
            "base_price": "000010000",
            "regular_lot_size": "00010",
            "listed_date": "20200102",
        }
    )
    part2 = _fixed_width_row(KOSPI_WIDTHS, KOSPI_PART2_COLUMNS, part2_values)
    content = "005930   KR7005930003삼성전자".ljust(30) + part2 + "\n"
    archive = _zip_bytes("kospi_code.mst", content)

    records = parse_symbol_master("KOSPI", archive)

    assert len(records) == 1
    record = records[0]
    assert record.market == "KOSPI"
    assert record.symbol == "005930"
    assert record.standard_code == "KR7005930003"
    assert record.korean_name == "삼성전자"
    assert record.currency == "KRW"
    assert record.country_code == "KR"
    assert record.base_price == 10000
    assert record.lot_size == 10
    assert record.listed_date == "20200102"
    assert record.raw["group_code"] == "ST"


def test_parse_overseas_master_normalizes_tab_separated_record() -> None:
    content = "\t".join(
        [
            "US",
            "NAS",
            "NASD",
            "NASDAQ",
            "AAPL",
            "AAPL",
            "애플",
            "Apple Inc.",
            "2",
            "USD",
            "2",
            "1",
            "000001234",
            "1",
            "1",
            "0930",
            "1600",
            "N",
            "",
            "IT",
            "0",
            "T",
            "004",
            "detail",
        ]
    )
    archive = _zip_bytes("nasmst.cod", content + "\n")

    records = parse_symbol_master("NASDAQ", archive)

    assert len(records) == 1
    record = records[0]
    assert record.market == "NASDAQ"
    assert record.symbol == "AAPL"
    assert record.realtime_symbol == "AAPL"
    assert record.korean_name == "애플"
    assert record.english_name == "Apple Inc."
    assert record.currency == "USD"
    assert record.exchange_name == "NASDAQ"
    assert record.country_code == "US"
    assert record.base_price == 1234
    assert record.lot_size == 1


def test_symbol_record_defaults_downloaded_at_to_kst() -> None:
    values = record_to_db_values(SymbolRecord(market="NASDAQ", symbol="AAPL"))

    assert str(values["downloaded_at"]).endswith("+09:00")


def test_symbols_download_command_upserts_downloaded_records(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "symbols.db"

    def fake_download_symbol_master(market: str) -> list[SymbolRecord]:
        return [
            SymbolRecord(
                market=market,
                symbol="AAPL",
                korean_name="애플",
                english_name="Apple Inc.",
                currency="USD",
                raw_source="nasmst.cod",
                raw={"symbol": "AAPL"},
                downloaded_at="2026-05-07T00:00:00+00:00",
            )
        ]

    monkeypatch.setattr(
        "kis_cli.services.symbols.download_symbol_master",
        fake_download_symbol_master,
    )

    result = runner.invoke(
        app,
        ["symbols", "download", "--market", "NASDAQ", "--db-path", str(db_path)],
    )

    assert result.exit_code == 0
    assert "Symbols downloaded" in result.output
    assert "NASDAQ" in result.output
    with connect(db_path) as connection:
        row = connection.execute(
            "SELECT market, symbol, korean_name, english_name FROM symbols"
        ).fetchone()

    assert row == ("NASDAQ", "AAPL", "애플", "Apple Inc.")
    runs = list_ingest_runs(tmp_path / "app.db")
    api_logs = list_api_logs(tmp_path / "app.db")

    assert len(runs) == 1
    assert runs[0].kind == "symbols"
    assert runs[0].market == "NASDAQ"
    assert runs[0].status == "success"
    assert runs[0].rows_written == 1
    assert runs[0].finished_at is not None
    assert api_logs[0]["endpoint"] == "symbol_master:NASDAQ"
    assert api_logs[0]["status_code"] == 200


def test_symbols_download_all_uses_progressbar(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "symbols.duckdb"
    calls: list[str] = []

    def fake_download_and_store_symbols(*, market: str, db_path, store: str, supabase_dsn: str | None):
        calls.append(market)
        assert store == "duckdb"
        assert supabase_dsn is None
        return SymbolDownloadResult(
            db_path=db_path,
            market=market,
            downloaded=1,
            stored=1,
        )

    monkeypatch.setattr("kis_cli.cli.symbols.ALL_SYMBOL_MARKETS", ("KOSPI", "NASDAQ"))
    monkeypatch.setattr(
        "kis_cli.cli.symbols.download_and_store_symbols",
        fake_download_and_store_symbols,
    )

    result = runner.invoke(
        app,
        ["symbols", "download", "--all", "--db-path", str(db_path)],
    )

    assert result.exit_code == 0
    assert calls == ["KOSPI", "NASDAQ"]
    assert "Downloading symbol masters" in result.output
    assert "Symbols downloaded" in result.output


def test_symbols_download_supabase_prompts_for_missing_dsn(tmp_path, monkeypatch) -> None:
    captured: dict[str, str | None] = {}

    def fake_download_and_store_symbols(*, market: str, db_path, store: str, supabase_dsn: str | None):
        captured["market"] = market
        captured["store"] = store
        captured["supabase_dsn"] = supabase_dsn
        return SymbolDownloadResult(
            db_path=None,
            market=market,
            downloaded=1,
            stored=1,
            store=store,
        )

    monkeypatch.delenv("KISCLI_SUPABASE_DB_DSN", raising=False)
    monkeypatch.setattr("kis_cli.cli.common.default_config_file", lambda: tmp_path / "config.yaml")
    monkeypatch.setattr(
        "kis_cli.cli.symbols.download_and_store_symbols",
        fake_download_and_store_symbols,
    )

    result = runner.invoke(
        app,
        ["symbols", "download", "--market", "NASDAQ", "--store", "supabase"],
        input="postgresql://prompted\n",
    )

    assert result.exit_code == 0
    assert captured == {
        "market": "NASDAQ",
        "store": "supabase",
        "supabase_dsn": "postgresql://prompted",
    }
    assert "Supabase PostgreSQL DSN" in result.output
    assert "postgresql://prompted" not in result.output


def _fixed_width_row(
    widths: list[int],
    columns: list[str],
    values: dict[str, str],
) -> str:
    parts = []
    for width, column in zip(widths, columns, strict=True):
        parts.append(values[column].ljust(width)[:width])
    return "".join(parts)


def _zip_bytes(name: str, content: str) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(name, content.encode("cp949"))
    return buffer.getvalue()
