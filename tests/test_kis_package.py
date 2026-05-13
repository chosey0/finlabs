from __future__ import annotations

import kis
from kis.auth import IssuedToken
from kis.chart import OverseasMinuteBar, parse_overseas_minute_bar
from kis.client import KisClient
from kis.price import CurrentPrice
from kis.symbols import SymbolRecord, normalize_market


def test_kis_package_reexports_core_library_api() -> None:
    assert kis.KisClient is KisClient
    assert kis.IssuedToken is IssuedToken
    assert kis.CurrentPrice is CurrentPrice
    assert kis.SymbolRecord is SymbolRecord
    assert kis.OverseasMinuteBar is OverseasMinuteBar
    assert normalize_market("nasdaq") == "NASDAQ"


def test_kis_chart_facade_parses_overseas_minute_bar() -> None:
    bar = parse_overseas_minute_bar(
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

    assert bar.local_date == "2024-02-22"
    assert bar.local_time == "16:00:00"
    assert bar.korea_date == "2024-02-23"
    assert bar.korea_time == "06:00:00"
