from __future__ import annotations

from decimal import Decimal

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.core.price import (
    CurrentPrice,
    parse_domestic_current_price,
    parse_overseas_current_price,
)

runner = CliRunner()


def test_parse_domestic_current_price_normalizes_common_fields() -> None:
    price = parse_domestic_current_price(
        market="KOSPI",
        symbol="005930",
        output={
            "hts_kor_isnm": "삼성전자",
            "stck_prpr": "70000",
            "prdy_vrss": "-100",
            "prdy_ctrt": "-0.14",
            "stck_oprc": "70100",
            "stck_hgpr": "70500",
            "stck_lwpr": "69900",
            "acml_vol": "1234567",
        },
    )

    assert price.market == "KOSPI"
    assert price.symbol == "005930"
    assert price.name == "삼성전자"
    assert price.price == Decimal("70000")
    assert price.currency == "KRW"
    assert price.change == Decimal("-100")
    assert price.change_rate == Decimal("-0.14")
    assert price.volume == 1234567


def test_parse_overseas_current_price_normalizes_common_fields() -> None:
    price = parse_overseas_current_price(
        market="NASDAQ",
        symbol="AAPL",
        output={
            "name": "Apple Inc.",
            "last": "190.25",
            "curr": "USD",
            "diff": "1.23",
            "rate": "0.65",
            "open": "189.00",
            "high": "191.00",
            "low": "188.50",
            "tvol": "987654",
        },
    )

    assert price.market == "NASDAQ"
    assert price.symbol == "AAPL"
    assert price.name == "Apple Inc."
    assert price.price == Decimal("190.25")
    assert price.currency == "USD"
    assert price.change == Decimal("1.23")
    assert price.change_rate == Decimal("0.65")
    assert price.volume == 987654


def test_price_current_command_prints_quote_without_secret_values(monkeypatch) -> None:
    def fake_get_current_price(
        *,
        symbol: str,
        market: str,
        profile: str | None = None,
        config_path=None,
    ) -> CurrentPrice:
        assert symbol == "AAPL"
        assert market == "NASDAQ"
        assert profile == "csq1404"
        return CurrentPrice(
            market="NASDAQ",
            symbol="AAPL",
            name="Apple Inc.",
            price=Decimal("190.25"),
            currency="USD",
            change=Decimal("1.23"),
            change_rate=Decimal("0.65"),
            open=Decimal("189.00"),
            high=Decimal("191.00"),
            low=Decimal("188.50"),
            volume=987654,
            raw={"access_token": "secret-token", "appkey": "secret-app-key"},
        )

    monkeypatch.setattr("kis_cli.cli.app.get_current_price", fake_get_current_price)

    result = runner.invoke(
        app,
        [
            "price",
            "current",
            "--symbol",
            "AAPL",
            "--market",
            "NASDAQ",
            "--profile",
            "csq1404",
        ],
    )

    assert result.exit_code == 0
    assert "Current price" in result.output
    assert "Apple Inc." in result.output
    assert "190.25" in result.output
    assert "secret-token" not in result.output
    assert "secret-app-key" not in result.output
