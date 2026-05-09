from __future__ import annotations

from decimal import Decimal

from kis_cli.core.auth import KisAuthError
from kis_cli.core.price import (
    CurrentPrice,
    parse_domestic_current_price,
    parse_overseas_current_price,
)
from kis_cli.services.price import get_current_price


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


def test_get_current_price_refreshes_token_once_after_auth_error(monkeypatch) -> None:
    refresh_flags: list[bool] = []
    attempts = {"count": 0}

    def fake_build_rest_client(*, profile=None, config_path=None, refresh=False):
        refresh_flags.append(refresh)
        return object()

    def fake_inquire_current_price(client, *, market: str, symbol: str) -> CurrentPrice:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise KisAuthError("token expired")
        return CurrentPrice(
            market=market,
            symbol=symbol,
            name="Apple Inc.",
            price=Decimal("190.25"),
            currency="USD",
            change=None,
            change_rate=None,
            open=None,
            high=None,
            low=None,
            volume=None,
        )

    monkeypatch.setattr("kis_cli.services.auth.build_rest_client", fake_build_rest_client)
    monkeypatch.setattr("kis_cli.services.price.inquire_current_price", fake_inquire_current_price)

    result = get_current_price(symbol="AAPL", market="NASDAQ", profile="csq1404")

    assert result.symbol == "AAPL"
    assert refresh_flags == [False, True]
    assert attempts["count"] == 2


def test_get_current_price_does_not_retry_more_than_once(monkeypatch) -> None:
    refresh_flags: list[bool] = []

    def fake_build_rest_client(*, profile=None, config_path=None, refresh=False):
        refresh_flags.append(refresh)
        return object()

    def always_fail(client, *, market: str, symbol: str) -> CurrentPrice:
        raise KisAuthError("token expired")

    monkeypatch.setattr("kis_cli.services.auth.build_rest_client", fake_build_rest_client)
    monkeypatch.setattr("kis_cli.services.price.inquire_current_price", always_fail)

    try:
        get_current_price(symbol="AAPL", market="NASDAQ", profile="csq1404")
    except KisAuthError:
        pass
    else:
        raise AssertionError("expected KisAuthError")

    assert refresh_flags == [False, True]
