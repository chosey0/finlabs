from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_cli.core.client import KisClient
from kis_cli.core.symbol_master import DOMESTIC_MARKETS, OVERSEAS_MARKET_CODES, normalize_market

DOMESTIC_CHART_PATH = "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice"
DOMESTIC_CHART_TR_ID = "FHKST03010100"
OVERSEAS_CHART_PATH = "/uapi/overseas-price/v1/quotations/inquire-daily-chartprice"
OVERSEAS_CHART_TR_ID = "FHKST03030100"
PERIOD_TO_INTERVAL = {"D": "1d", "W": "1w", "M": "1mo", "Y": "1y"}
OVERSEAS_CHART_CONDITION_CODES = {
    "OVERSEAS_INDEX": "N",
    "OVERSEAS_EXCHANGE_RATE": "X",
    "OVERSEAS_BOND": "I",
    "GOLD_FUTURES": "S",
}


@dataclass(frozen=True)
class OhlcvBar:
    market: str
    symbol: str
    interval: str
    timestamp: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    raw: dict[str, Any] = field(default_factory=dict)


def normalize_period(period: str) -> str:
    normalized = period.strip().upper()
    if normalized not in PERIOD_TO_INTERVAL:
        raise ValueError("period must be one of: D, W, M, Y")
    return normalized


def normalize_chart_market(market: str) -> str:
    normalized = market.strip().upper().replace("-", "_")
    if normalized in OVERSEAS_CHART_CONDITION_CODES:
        return normalized
    return normalize_market(normalized)


def fetch_ohlcv_history(
    client: KisClient,
    *,
    market: str,
    symbol: str,
    start: str,
    end: str,
    period: str,
    adjusted: bool = True,
    max_pages: int = 100,
) -> list[OhlcvBar]:
    normalized_market = normalize_chart_market(market)
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")
    start_date = parse_date(start)
    end_date = parse_date(end)
    if start_date > end_date:
        raise ValueError("start must be on or before end")
    normalized_period = normalize_period(period)

    if normalized_market in DOMESTIC_MARKETS:
        return fetch_domestic_ohlcv_history(
            client,
            market=normalized_market,
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
            period=normalized_period,
            adjusted=adjusted,
            max_pages=max_pages,
        )
    return fetch_overseas_ohlcv_history(
        client,
        market=normalized_market,
        symbol=normalized_symbol,
        start_date=start_date,
        end_date=end_date,
        period=normalized_period,
        max_pages=max_pages,
    )


def fetch_domestic_ohlcv_history(
    client: KisClient,
    *,
    market: str,
    symbol: str,
    start_date: date,
    end_date: date,
    period: str,
    adjusted: bool,
    max_pages: int,
) -> list[OhlcvBar]:
    bars: dict[str, OhlcvBar] = {}
    page_end = end_date

    for _ in range(max_pages):
        response = client.get(
            DOMESTIC_CHART_PATH,
            tr_id=DOMESTIC_CHART_TR_ID,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": format_date(start_date),
                "FID_INPUT_DATE_2": format_date(page_end),
                "FID_PERIOD_DIV_CODE": period,
                "FID_ORG_ADJ_PRC": "0" if adjusted else "1",
            },
        )
        rows = _output_rows(response)
        parsed = [
            bar
            for bar in (
                parse_domestic_ohlcv_bar(market=market, symbol=symbol, interval=PERIOD_TO_INTERVAL[period], row=row)
                for row in rows
            )
            if start_date <= parse_date(bar.timestamp) <= end_date
        ]
        if not parsed:
            break

        for bar in parsed:
            bars[bar.timestamp] = bar

        oldest = min(parse_date(bar.timestamp) for bar in parsed)
        if oldest <= start_date:
            break
        next_end = oldest - timedelta(days=1)
        if next_end >= page_end:
            break
        page_end = next_end

    return _sorted_bars(bars.values())


def fetch_overseas_ohlcv_history(
    client: KisClient,
    *,
    market: str,
    symbol: str,
    start_date: date,
    end_date: date,
    period: str,
    max_pages: int,
) -> list[OhlcvBar]:
    bars: dict[str, OhlcvBar] = {}
    tr_cont = ""

    for _ in range(max_pages):
        response = client.get_response(
            OVERSEAS_CHART_PATH,
            tr_id=OVERSEAS_CHART_TR_ID,
            tr_cont=tr_cont,
            params={
                "FID_COND_MRKT_DIV_CODE": _overseas_condition_code(market, symbol),
                "FID_INPUT_ISCD": symbol,
                "FID_INPUT_DATE_1": format_date(start_date),
                "FID_INPUT_DATE_2": format_date(end_date),
                "FID_PERIOD_DIV_CODE": period,
            },
        )
        rows = _output_rows(response.payload)
        parsed = [
            bar
            for bar in (
                parse_overseas_ohlcv_bar(market=market, symbol=symbol, interval=PERIOD_TO_INTERVAL[period], row=row)
                for row in rows
            )
            if start_date <= parse_date(bar.timestamp) <= end_date
        ]
        for bar in parsed:
            bars[bar.timestamp] = bar

        continuation = response.headers.get("tr_cont", "")
        if continuation not in {"M", "F"}:
            break
        tr_cont = "N"

    return _sorted_bars(bars.values())


def parse_domestic_ohlcv_bar(
    *,
    market: str,
    symbol: str,
    interval: str,
    row: dict[str, Any],
) -> OhlcvBar:
    return OhlcvBar(
        market=market,
        symbol=symbol,
        interval=interval,
        timestamp=_date_value(row, "stck_bsop_date", "bsop_date"),
        open=_required_decimal(row, "stck_oprc"),
        high=_required_decimal(row, "stck_hgpr"),
        low=_required_decimal(row, "stck_lwpr"),
        close=_required_decimal(row, "stck_clpr"),
        volume=_required_int(row, "acml_vol"),
        raw=row,
    )


def parse_overseas_ohlcv_bar(
    *,
    market: str,
    symbol: str,
    interval: str,
    row: dict[str, Any],
) -> OhlcvBar:
    return OhlcvBar(
        market=market,
        symbol=symbol,
        interval=interval,
        timestamp=_date_value(row, "xymd", "date", "stck_bsop_date"),
        open=_required_decimal(row, "open", "ovrs_nmix_oprc"),
        high=_required_decimal(row, "high", "ovrs_nmix_hgpr"),
        low=_required_decimal(row, "low", "ovrs_nmix_lwpr"),
        close=_required_decimal(row, "clos", "close", "ovrs_nmix_prpr"),
        volume=_required_int(row, "tvol", "volume", "acml_vol"),
        raw=row,
    )


def parse_date(value: str) -> date:
    text = value.strip()
    if len(text) == 8 and text.isdigit():
        return datetime.strptime(text, "%Y%m%d").date()
    return date.fromisoformat(text)


def format_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def bar_to_db_values(bar: OhlcvBar) -> dict[str, object]:
    return {
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


def _output_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    output = payload.get("output2") or payload.get("output")
    if output is None:
        return []
    if isinstance(output, dict):
        return [output]
    if isinstance(output, list):
        return [row for row in output if isinstance(row, dict)]
    raise ValueError("KIS response output rows had an unsupported shape")


def _overseas_condition_code(market: str, symbol: str) -> str:
    if market in OVERSEAS_CHART_CONDITION_CODES:
        return OVERSEAS_CHART_CONDITION_CODES[market]
    if market in OVERSEAS_MARKET_CODES:
        return "N" if symbol.startswith(".") else "N"
    return "N"


def _date_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return parse_date(value).isoformat()
    raise ValueError(f"missing date field; expected one of: {', '.join(keys)}")


def _required_decimal(row: dict[str, Any], *keys: str) -> Decimal:
    for key in keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip().replace(",", "")
        if not text:
            continue
        try:
            return Decimal(text)
        except InvalidOperation:
            continue
    raise ValueError(f"missing numeric field; expected one of: {', '.join(keys)}")


def _required_int(row: dict[str, Any], *keys: str) -> int:
    value = _required_decimal(row, *keys)
    return int(value)


def _sorted_bars(bars) -> list[OhlcvBar]:
    return sorted(bars, key=lambda bar: bar.timestamp)
