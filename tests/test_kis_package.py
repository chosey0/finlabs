from __future__ import annotations

import zipfile
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from io import BytesIO

import kis
from kis import (
    Credentials,
    KisClient,
    KisConfigError,
    MockNotSupportedError,
    parse_domestic_current_price,
    parse_overseas_minute_bar,
)
from kis.auth import IssuedToken, parse_token_response
from kis.parsers import output_rows
from kis.symbols import parse_symbol_master


def test_kis_package_exports_core_sdk_api() -> None:
    assert kis.KisClient is KisClient
    assert kis.Credentials is Credentials
    assert kis.IssuedToken is IssuedToken
    assert kis.__version__ == "0.1.0"
    assert "domestic.price.current" in kis.names()
    assert "overseas.chart.minute" in kis.names()


def test_endpoint_registry_rejects_mock_for_unsupported_endpoint() -> None:
    spec = kis.lookup("overseas.chart.minute")

    try:
        spec.tr_id_for("mock")
    except MockNotSupportedError as exc:
        assert exc.endpoint_name == "overseas.chart.minute"
    else:
        raise AssertionError("expected MockNotSupportedError")


def test_endpoint_registry_rejects_invalid_environment() -> None:
    spec = kis.lookup("domestic.price.current")

    try:
        spec.tr_id_for("dev")  # type: ignore[arg-type]
    except KisConfigError as exc:
        assert "environment must be one of" in str(exc)
    else:
        raise AssertionError("expected KisConfigError")


def test_kis_parsers_normalize_rest_payloads() -> None:
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
            "acml_vol": "1,234",
        },
    )
    minute = parse_overseas_minute_bar(
        market="NASDAQ",
        symbol="AAPL",
        interval_minutes=5,
        row={
            "tymd": "20240222",
            "xymd": "20240222",
            "xhms": "160000",
            "kymd": "20240223",
            "khms": "060000",
            "open": "197.3400",
            "high": "197.4100",
            "low": "197.2800",
            "last": "197.4100",
            "evol": "5695",
            "eamt": "1123799",
        },
    )

    assert price.name == "삼성전자"
    assert price.price == Decimal("70000")
    assert price.volume == 1234
    assert minute.local_date == "2024-02-22"
    assert minute.korea_time == "06:00:00"


def test_kis_auth_and_response_helpers() -> None:
    issued_at = datetime(2026, 5, 13, 1, 0, tzinfo=UTC)

    token = parse_token_response(
        {
            "access_token": "secret-token",
            "token_type": "Bearer",
            "expires_in": "3600",
        },
        issued_at=issued_at,
    )

    assert token.expires_at == issued_at + timedelta(seconds=3600)
    assert output_rows({"output": {"symbol": "AAPL"}}) == [{"symbol": "AAPL"}]
    assert output_rows({"output": {"summary": "not a row"}, "output2": []}) == []


def test_kis_symbol_master_parser_handles_overseas_zip() -> None:
    zip_bytes = BytesIO()
    with zipfile.ZipFile(zip_bytes, "w") as archive:
        archive.writestr(
            "nasmst.cod",
            "\t".join(
                [
                    "US",
                    "NAS",
                    "NASDAQ",
                    "NASDAQ",
                    "AAPL",
                    "DNAAPL",
                    "애플",
                    "Apple Inc",
                    "STOCK",
                    "USD",
                    "2",
                    "0",
                    "19700",
                    "1",
                    "1",
                    "093000",
                    "160000",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                ]
            ).encode("cp949"),
        )

    records = parse_symbol_master("NASDAQ", zip_bytes.getvalue())

    assert len(records) == 1
    assert records[0].symbol == "AAPL"
    assert records[0].english_name == "Apple Inc"
    assert records[0].currency == "USD"
