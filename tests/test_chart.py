from __future__ import annotations

import asyncio
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from typer.testing import CliRunner

from kis import (
    KisAuthError,
    OhlcvBar,
    parse_domestic_ohlcv_bar,
    parse_overseas_minute_bar,
    parse_overseas_ohlcv_bar,
)
from kis.domestic.chart import DomesticChartAPI
from kis.endpoints.registry import lookup
from kis.overseas.chart import OverseasChartAPI

from kis_cli.cli.app import app
from kis_cli.services.chart import collect_ohlcv_history
from kis_cli.storage import connect, init_database
from kis_cli.storage.app_repositories import list_api_logs, list_ingest_runs
from kis_cli.storage.repositories import insert_ohlcv_bars, insert_symbol

runner = CliRunner()


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    async def request(self, spec, *, params: dict[str, str], **kwargs):
        self.calls.append((spec.path, spec.tr_id_real, params, kwargs.get("tr_cont", "")))
        path = spec.path
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
    assert bar.change == Decimal("7")
    assert bar.change_rate == Decimal("7.00")
    assert bar.amount == Decimal("107000")


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
    assert bar.change == Decimal("3.5")
    assert bar.change_rate == Decimal("1.72")
    assert bar.amount == Decimal("414000")


def test_parse_overseas_minute_bar() -> None:
    bar = parse_overseas_minute_bar(
        market="NASDAQ",
        symbol="NVDA",
        interval_minutes=5,
        row=_overseas_minute_row("20241014", "140600"),
    )

    assert bar.market == "NASDAQ"
    assert bar.symbol == "NVDA"
    assert bar.interval_minutes == 5
    assert bar.local_business_date == "2024-10-14"
    assert bar.local_date == "2024-10-14"
    assert bar.local_time == "14:06:00"
    assert bar.korea_date == "2024-10-15"
    assert bar.korea_time == "03:06:00"
    assert bar.open == Decimal("130")
    assert bar.high == Decimal("131")
    assert bar.low == Decimal("129")
    assert bar.close == Decimal("130.5")
    assert bar.volume == 1000
    assert bar.amount == Decimal("130500")


def test_overseas_stock_minute_history_uses_previous_last_bar_keyb() -> None:
    class MinuteClient:
        def __init__(self) -> None:
            self.calls = []

        async def request(self, spec, *, params: dict[str, str], **kwargs):
            self.calls.append((spec.path, spec.tr_id_real, params, kwargs.get("tr_cont", "")))
            if params["KEYB"] == "":
                return {
                    "rt_cd": "0",
                    "output1": {"next": "1"},
                    "output2": [
                        _overseas_minute_row("20241014", "140600"),
                        _overseas_minute_row("20241014", "140100"),
                    ],
                }
            return {
                "rt_cd": "0",
                "output1": {"next": "0"},
                "output2": [_overseas_minute_row("20241014", "135600")],
            }

    client = MinuteClient()

    bars = asyncio.run(
        OverseasChartAPI(client).minute(
            symbol="NVDA",
            exchange="NAS",
            market="NASDAQ",
            start="2024-10-14 13:56:00",
            interval_minutes=5,
            count=120,
            include_previous=True,
        )
    )

    assert client.calls[0][0] == "/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice"
    assert client.calls[0][1] == "HHDFS76950200"
    assert client.calls[0][2]["KEYB"] == ""
    assert client.calls[0][2]["NEXT"] == ""
    assert client.calls[0][2]["NMIN"] == "5"
    assert client.calls[0][2]["PINC"] == "1"
    assert client.calls[1][2]["KEYB"] == "20241014135600"
    assert client.calls[1][2]["NEXT"] == "1"
    assert [f"{bar.local_date} {bar.local_time}" for bar in bars] == [
        "2024-10-14 13:56:00",
        "2024-10-14 14:01:00",
        "2024-10-14 14:06:00",
    ]


def test_domestic_history_continues_by_moving_end_date() -> None:
    client = FakeClient()

    bars = asyncio.run(
        DomesticChartAPI(client).daily(
            market="KOSPI",
            symbol="005930",
            start=__import__("datetime").date(2026, 5, 4),
            end=__import__("datetime").date(2026, 5, 7),
            adjusted=True,
            max_pages=10,
        )
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

    bars = asyncio.run(
        OverseasChartAPI(client).daily(
            symbol="AAPL",
            exchange="NAS",
            market="NASDAQ",
            start=__import__("datetime").date(2026, 5, 6),
            end=__import__("datetime").date(2026, 5, 7),
            period="D",
            adjusted=True,
            max_pages=10,
        )
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

        async def request(self, spec, *, params: dict[str, str], **kwargs):
            self.calls.append((spec.path, spec.tr_id_real, params, kwargs.get("tr_cont", "")))
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

    bars = asyncio.run(
        OverseasChartAPI(client).daily(
            symbol="NVDA",
            exchange="NAS",
            market="NASDAQ",
            start=date(2026, 1, 27),
            end=date(2026, 5, 7),
            period="D",
            adjusted=True,
            max_pages=10,
        )
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
        asyncio.run(
            OverseasChartAPI(client).daily(
                symbol="AAPL",
                exchange="NAS",
                market="NASDAQ",
                start="2026-01-01",
                end="2026-05-07",
                period="Y",
            )
        )
    except ValueError as exc:
        assert "supports period D, W, or M" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_overseas_special_history_keeps_chartprice_api() -> None:
    spec = lookup("overseas.chart.ohlcv")

    assert spec.path == "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
    assert spec.tr_id_real == "FHKST03030100"
    assert "FID_PERIOD_DIV_CODE" in spec.required_params


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
        change=Decimal("7"),
        change_rate=Decimal("7.00"),
        amount=Decimal("107000"),
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
        "change": float(bar.change),
        "change_rate": float(bar.change_rate),
        "amount": float(bar.amount),
    }

    with connect(db_path) as connection:
        first = insert_ohlcv_bars(connection, [values])
        duplicate = insert_ohlcv_bars(connection, [values])
        duplicate_batch = insert_ohlcv_bars(connection, [values, values])
        stored = connection.execute(
            """
            SELECT change, change_rate, amount
            FROM ohlcv_bars
            WHERE symbol = '005930'
            """
        ).fetchone()

    assert first == 1
    assert duplicate == 0
    assert duplicate_batch == 0
    assert stored == (7.0, 7.0, 107000.0)


def test_collect_ohlcv_history_resolves_market_from_symbol_table(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "chart.db"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_symbol(connection, market="NASDAQ", symbol="NVDA", name="NVIDIA")

    def fake_call_with_sdk_client(operation, **kwargs):
        return asyncio.run(operation(object()))

    async def fake_fetch_ohlcv_history(client, **kwargs):
        assert kwargs["market"] == "NASDAQ"
        assert kwargs["symbol"] == "NVDA"
        assert kwargs["end"] == date.today().isoformat()
        return [
            OhlcvBar(
                market="NASDAQ",
                symbol="NVDA",
                interval="1d",
                timestamp=date.today().isoformat(),
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=1000,
            )
        ]

    monkeypatch.setattr(
        "kis_cli.services.chart.call_with_sdk_client",
        fake_call_with_sdk_client,
    )
    monkeypatch.setattr("kis_cli.services.chart._fetch_ohlcv_history_async", fake_fetch_ohlcv_history)

    result = collect_ohlcv_history(
        symbol="nvda",
        start="2026-01-01",
        end=None,
        period="D",
        db_path=db_path,
    )

    assert result.market == "NASDAQ"
    assert result.symbol == "NVDA"
    assert result.fetched == 1


def test_collect_ohlcv_history_refreshes_token_after_auth_error(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "chart.db"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_symbol(connection, market="NASDAQ", symbol="AAPL", name="Apple")

    attempts = {"count": 0}

    async def fake_fetch_ohlcv_history(client, **kwargs):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise KisAuthError("token expired")
        return [
            OhlcvBar(
                market="NASDAQ",
                symbol="AAPL",
                interval="1d",
                timestamp="2026-05-07",
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=1000,
            )
        ]

    def fake_call_with_sdk_client(operation, **kwargs):
        try:
            return asyncio.run(operation(object()))
        except KisAuthError:
            return asyncio.run(operation(object()))

    monkeypatch.setattr("kis_cli.services.chart.call_with_sdk_client", fake_call_with_sdk_client)
    monkeypatch.setattr("kis_cli.services.chart._fetch_ohlcv_history_async", fake_fetch_ohlcv_history)

    result = collect_ohlcv_history(
        symbol="AAPL",
        start="2026-05-01",
        end="2026-05-07",
        period="D",
        db_path=db_path,
    )

    assert result.fetched == 1
    assert attempts["count"] == 2


def test_collect_ohlcv_history_records_saved_ingest_run(monkeypatch, tmp_path: Path) -> None:
    db_path = tmp_path / "chart.db"
    init_database(db_path)
    with connect(db_path) as connection:
        insert_symbol(connection, market="NASDAQ", symbol="AAPL", name="Apple")

    def fake_call_with_sdk_client(operation, **kwargs):
        return asyncio.run(operation(object()))

    async def fake_fetch_ohlcv_history(client, **kwargs):
        return [
            OhlcvBar(
                market="NASDAQ",
                symbol="AAPL",
                interval="1d",
                timestamp="2026-05-07",
                open=Decimal("100"),
                high=Decimal("110"),
                low=Decimal("90"),
                close=Decimal("105"),
                volume=1000,
            )
        ]

    monkeypatch.setattr(
        "kis_cli.services.chart.call_with_sdk_client",
        fake_call_with_sdk_client,
    )
    monkeypatch.setattr("kis_cli.services.chart._fetch_ohlcv_history_async", fake_fetch_ohlcv_history)

    result = collect_ohlcv_history(
        symbol="AAPL",
        start="2026-05-01",
        end="2026-05-07",
        period="D",
        db_path=db_path,
        save=True,
    )

    runs = list_ingest_runs(tmp_path / "app.db")
    api_logs = list_api_logs(tmp_path / "app.db")
    assert result.stored == 1
    assert len(runs) == 1
    assert runs[0].kind == "ohlcv:1d"
    assert runs[0].market == "NASDAQ"
    assert runs[0].symbol == "AAPL"
    assert runs[0].status == "success"
    assert runs[0].rows_written == 1
    assert runs[0].finished_at is not None
    assert api_logs[0]["endpoint"] == "ohlcv:NASDAQ:1d"
    assert api_logs[0]["status_code"] == 200


def test_chart_daily_command_prints_summary(monkeypatch, tmp_path: Path) -> None:
    def fake_collect_ohlcv_history(**kwargs):
        assert kwargs["symbol"] == "005930"
        assert "market" not in kwargs
        assert kwargs["period"] == "D"
        assert kwargs["end"] is None
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

    monkeypatch.setattr("kis_cli.cli.chart.collect_ohlcv_history", fake_collect_ohlcv_history)

    result = runner.invoke(
        app,
        [
            "chart",
            "daily",
            "--symbol",
            "005930",
            "--start",
            "2026-05-01",
            "--save",
        ],
    )

    assert result.exit_code == 0
    assert "OHLCV history" in result.output
    assert "Fetched" in result.output
    assert "Stored" in result.output


def test_chart_minutes_command_uses_required_start_without_max_pages(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_collect_overseas_minutes(**kwargs):
        captured.update(kwargs)
        return __import__("kis_cli.services.chart").services.chart.OverseasMinuteResult(
            db_path=tmp_path / "chart.db",
            market="NASDAQ",
            symbol="NVDA",
            interval_minutes=5,
            fetched=1,
            stored=1,
            bars=[],
        )

    monkeypatch.setattr("kis_cli.cli.chart.collect_overseas_minutes", fake_collect_overseas_minutes)

    result = runner.invoke(
        app,
        [
            "chart",
            "minutes",
            "--symbol",
            "NVDA",
            "--start",
            "2024-10-14 14:01:00",
            "--interval-minutes",
            "5",
            "--save",
        ],
    )

    assert result.exit_code == 0
    assert captured["symbol"] == "NVDA"
    assert captured["start"] == "2024-10-14 14:01:00"
    assert captured["interval_minutes"] == 5
    assert "max_pages" not in captured
    assert "Overseas minute bars" in result.output
    assert "Fetched" in result.output


def test_chart_daily_supabase_prompts_for_missing_dsn(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def fake_collect_ohlcv_history(**kwargs):
        captured.update(kwargs)
        return __import__("kis_cli.services.chart").services.chart.ChartHistoryResult(
            db_path=None,
            market="NASDAQ",
            symbol="AAPL",
            interval="1d",
            fetched=1,
            stored=1,
            bars=[
                OhlcvBar(
                    market="NASDAQ",
                    symbol="AAPL",
                    interval="1d",
                    timestamp="2026-05-07",
                    open=Decimal("100"),
                    high=Decimal("110"),
                    low=Decimal("90"),
                    close=Decimal("107"),
                    volume=1000,
                )
            ],
            store="supabase",
    )

    monkeypatch.delenv("KISCLI_SUPABASE_DB_DSN", raising=False)
    monkeypatch.setattr("kis_cli.cli.common.default_config_file", lambda: tmp_path / "config.yaml")
    monkeypatch.setattr("kis_cli.cli.chart.collect_ohlcv_history", fake_collect_ohlcv_history)

    result = runner.invoke(
        app,
        [
            "chart",
            "daily",
            "--symbol",
            "AAPL",
            "--start",
            "2026-05-01",
            "--save",
            "--store",
            "supabase",
        ],
        input="postgresql://prompted\n",
    )

    assert result.exit_code == 0
    assert captured["store"] == "supabase"
    assert captured["supabase_dsn"] == "postgresql://prompted"
    assert "Supabase PostgreSQL DSN" in result.output
    assert "postgresql://prompted" not in result.output


def _domestic_row(date: str, close: str) -> dict[str, str]:
    return {
        "stck_bsop_date": date,
        "stck_oprc": "100",
        "stck_hgpr": "110",
        "stck_lwpr": "90",
        "stck_clpr": close,
        "acml_vol": "1000",
        "prdy_vrss": "7",
        "prdy_ctrt": "7.00",
        "acml_tr_pbmn": "107000",
    }


def _overseas_row(date: str, close: str) -> dict[str, str]:
    return {
        "xymd": date,
        "open": "200",
        "high": "210",
        "low": "190",
        "clos": close,
        "tvol": "2000",
        "diff": "3.5",
        "rate": "1.72",
        "tamt": "414000",
    }


def _overseas_chartprice_row(date: str, close: str) -> dict[str, str]:
    return {
        "stck_bsop_date": date,
        "ovrs_nmix_oprc": "300",
        "ovrs_nmix_hgpr": "310",
        "ovrs_nmix_lwpr": "290",
        "ovrs_nmix_prpr": close,
        "acml_vol": "3000",
        "ovrs_nmix_prdy_vrss": "7",
        "prdy_ctrt": "2.33",
    }


def _overseas_minute_row(date: str, time: str) -> dict[str, str]:
    return {
        "tymd": date,
        "xymd": date,
        "xhms": time,
        "kymd": "20241015",
        "khms": "030600",
        "open": "130",
        "high": "131",
        "low": "129",
        "last": "130.5",
        "evol": "1000",
        "eamt": "130500",
    }
