from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.core.chart import (
    OhlcvBar,
    fetch_ohlcv_history,
    fetch_domestic_ohlcv_history,
    fetch_overseas_ohlcv_history,
    fetch_overseas_stock_period_history,
    parse_domestic_ohlcv_bar,
    parse_overseas_ohlcv_bar,
)
from kis_cli.storage import connect, init_database
from kis_cli.storage.repositories import insert_ohlcv_bars

runner = CliRunner()


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def get(self, path: str, *, tr_id: str, params: dict[str, str], tr_cont: str = ""):
        self.calls.append((path, tr_id, params, tr_cont))
        if "dailyprice" in path:
            if params["KEYB"] == "":
                return {
                    "rt_cd": "0",
                    "KEYB": "1",
                    "output2": [_overseas_row("20260507", "207")],
                }
            return {
                "rt_cd": "0",
                "output2": [_overseas_row("20260506", "206")],
            }
        if "inquire-daily-chartprice" in path:
            return {
                "rt_cd": "0",
                "output2": [_overseas_chartprice_row("20260507", "307")],
            }
        end = params["FID_INPUT_DATE_2"]
        if end == "20260507":
            rows = [
                _domestic_row("20260507", "107"),
                _domestic_row("20260506", "106"),
            ]
        else:
            rows = [
                _domestic_row("20260505", "105"),
                _domestic_row("20260504", "104"),
            ]
        return {"rt_cd": "0", "output2": rows}

    def get_response(self, path: str, *, tr_id: str, params: dict[str, str], tr_cont: str = ""):
        self.calls.append((path, tr_id, params, tr_cont))
        if tr_cont == "":
            return FakeResponse(
                {"rt_cd": "0", "output2": [_overseas_row("20260507", "207")]},
                {"tr_cont": "M"},
            )
        return FakeResponse(
            {"rt_cd": "0", "output2": [_overseas_row("20260506", "206")]},
            {"tr_cont": ""},
        )


class FakeResponse:
    def __init__(self, payload, headers) -> None:
        self.payload = payload
        self.headers = headers


def test_parse_domestic_ohlcv_bar() -> None:
    bar = parse_domestic_ohlcv_bar(
        market="KOSPI",
        symbol="005930",
        interval="1d",
        row=_domestic_row("20260507", "107"),
    )

    assert bar.timestamp == "2026-05-07"
    assert bar.open == Decimal("100")
    assert bar.high == Decimal("110")
    assert bar.low == Decimal("90")
    assert bar.close == Decimal("107")
    assert bar.volume == 1000


def test_parse_overseas_ohlcv_bar() -> None:
    bar = parse_overseas_ohlcv_bar(
        market="NASDAQ",
        symbol="AAPL",
        interval="1d",
        row=_overseas_row("20260507", "207"),
    )

    assert bar.timestamp == "2026-05-07"
    assert bar.close == Decimal("207")
    assert bar.volume == 2000


def test_domestic_history_continues_by_moving_end_date() -> None:
    client = FakeClient()

    bars = fetch_domestic_ohlcv_history(
        client,
        market="KOSPI",
        symbol="005930",
        start_date=__import__("datetime").date(2026, 5, 4),
        end_date=__import__("datetime").date(2026, 5, 7),
        period="D",
        adjusted=True,
        max_pages=10,
    )

    assert [bar.timestamp for bar in bars] == [
        "2026-05-04",
        "2026-05-05",
        "2026-05-06",
        "2026-05-07",
    ]
    assert client.calls[0][2]["FID_INPUT_DATE_2"] == "20260507"
    assert client.calls[1][2]["FID_INPUT_DATE_2"] == "20260505"


def test_overseas_stock_period_history_uses_dailyprice_keyb() -> None:
    client = FakeClient()

    bars = fetch_overseas_stock_period_history(
        client,
        market="NASDAQ",
        symbol="AAPL",
        start_date=__import__("datetime").date(2026, 5, 6),
        end_date=__import__("datetime").date(2026, 5, 7),
        period="D",
        adjusted=True,
        max_pages=10,
    )

    assert [bar.timestamp for bar in bars] == ["2026-05-06", "2026-05-07"]
    assert client.calls[0][0] == "/uapi/overseas-price/v1/quotations/dailyprice"
    assert client.calls[0][1] == "HHDFS76240000"
    assert client.calls[0][2]["EXCD"] == "NAS"
    assert client.calls[0][2]["GUBN"] == "0"
    assert client.calls[0][2]["MODP"] == "1"
    assert client.calls[0][2]["KEYB"] == ""
    assert client.calls[1][2]["KEYB"] == "1"


def test_overseas_stock_period_history_falls_back_to_moving_bymd_without_keyb() -> None:
    class NoKeybClient:
        def __init__(self) -> None:
            self.calls = []

        def get(self, path: str, *, tr_id: str, params: dict[str, str], tr_cont: str = ""):
            self.calls.append((path, tr_id, params, tr_cont))
            if params["BYMD"] == "20260507":
                end = date(2026, 5, 7)
                return {
                    "rt_cd": "0",
                    "output2": [
                        _overseas_row((end - timedelta(days=offset)).strftime("%Y%m%d"), str(300 - offset))
                        for offset in range(100)
                    ],
                }
            return {
                "rt_cd": "0",
                "output2": [_overseas_row("20260127", "199")],
            }

    client = NoKeybClient()

    bars = fetch_overseas_stock_period_history(
        client,
        market="NASDAQ",
        symbol="NVDA",
        start_date=date(2026, 1, 27),
        end_date=date(2026, 5, 7),
        period="D",
        adjusted=True,
        max_pages=10,
    )

    assert len(client.calls) == 2
    assert client.calls[0][2]["BYMD"] == "20260507"
    assert client.calls[1][2]["BYMD"] == "20260127"
    assert client.calls[1][2]["KEYB"] == ""
    assert bars[0].timestamp == "2026-01-27"
    assert bars[-1].timestamp == "2026-05-07"


def test_overseas_stock_yearly_history_is_unsupported() -> None:
    client = FakeClient()

    try:
        fetch_ohlcv_history(
            client,
            market="NASDAQ",
            symbol="AAPL",
            start="2026-01-01",
            end="2026-05-07",
            period="Y",
        )
    except ValueError as exc:
        assert "supports only D, W, or M" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_overseas_special_history_keeps_chartprice_api() -> None:
    client = FakeClient()

    bars = fetch_overseas_ohlcv_history(
        client,
        market="OVERSEAS_INDEX",
        symbol=".IXIC",
        start_date=__import__("datetime").date(2026, 5, 7),
        end_date=__import__("datetime").date(2026, 5, 7),
        period="Y",
        max_pages=10,
    )

    assert [bar.timestamp for bar in bars] == ["2026-05-07"]
    assert client.calls[0][0] == "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
    assert client.calls[0][1] == "FHKST03030100"
    assert client.calls[0][2]["FID_COND_MRKT_DIV_CODE"] == "N"
    assert client.calls[0][2]["FID_PERIOD_DIV_CODE"] == "Y"


def test_insert_ohlcv_bars_ignores_duplicates(tmp_path: Path) -> None:
    db_path = tmp_path / "chart.db"
    init_database(db_path)
    bar = OhlcvBar(
        market="KOSPI",
        symbol="005930",
        interval="1d",
        timestamp="2026-05-07",
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("107"),
        volume=1000,
    )
    values = {
        "market": bar.market,
        "symbol": bar.symbol,
        "interval": bar.interval,
        "timestamp": bar.timestamp,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": bar.volume,
    }

    with connect(db_path) as connection:
        first = insert_ohlcv_bars(connection, [values])
        duplicate = insert_ohlcv_bars(connection, [values])

    assert first == 1
    assert duplicate == 0


def test_chart_daily_command_prints_summary(monkeypatch, tmp_path: Path) -> None:
    def fake_collect_ohlcv_history(**kwargs):
        assert kwargs["symbol"] == "005930"
        assert kwargs["market"] == "KOSPI"
        assert kwargs["period"] == "D"
        return __import__("kis_cli.services.chart").services.chart.ChartHistoryResult(
            db_path=tmp_path / "chart.db",
            market="KOSPI",
            symbol="005930",
            interval="1d",
            fetched=1,
            stored=1,
            bars=[
                OhlcvBar(
                    market="KOSPI",
                    symbol="005930",
                    interval="1d",
                    timestamp="2026-05-07",
                    open=Decimal("100"),
                    high=Decimal("110"),
                    low=Decimal("90"),
                    close=Decimal("107"),
                    volume=1000,
                )
            ],
        )

    monkeypatch.setattr("kis_cli.cli.app.collect_ohlcv_history", fake_collect_ohlcv_history)

    result = runner.invoke(
        app,
        [
            "chart",
            "daily",
            "--symbol",
            "005930",
            "--market",
            "KOSPI",
            "--start",
            "2026-05-01",
            "--end",
            "2026-05-07",
            "--save",
        ],
    )

    assert result.exit_code == 0
    assert "OHLCV history" in result.output
    assert "Fetched" in result.output
    assert "Stored" in result.output


def _domestic_row(date: str, close: str) -> dict[str, str]:
    return {
        "stck_bsop_date": date,
        "stck_oprc": "100",
        "stck_hgpr": "110",
        "stck_lwpr": "90",
        "stck_clpr": close,
        "acml_vol": "1000",
    }


def _overseas_row(date: str, close: str) -> dict[str, str]:
    return {
        "xymd": date,
        "open": "200",
        "high": "210",
        "low": "190",
        "clos": close,
        "tvol": "2000",
    }


def _overseas_chartprice_row(date: str, close: str) -> dict[str, str]:
    return {
        "stck_bsop_date": date,
        "ovrs_nmix_oprc": "300",
        "ovrs_nmix_hgpr": "310",
        "ovrs_nmix_lwpr": "290",
        "ovrs_nmix_prpr": close,
        "acml_vol": "3000",
    }
