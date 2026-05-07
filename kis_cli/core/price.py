from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from kis_cli.core.client import KisClient
from kis_cli.core.symbol_master import DOMESTIC_MARKETS, OVERSEAS_MARKET_CODES, normalize_market

DOMESTIC_PRICE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
DOMESTIC_PRICE_TR_ID = "FHKST01010100"
OVERSEAS_PRICE_PATH = "/uapi/overseas-price/v1/quotations/price"
OVERSEAS_PRICE_TR_ID = "HHDFS00000300"


@dataclass(frozen=True)
class CurrentPrice:
    market: str
    symbol: str
    name: str
    price: Decimal | None
    currency: str
    change: Decimal | None
    change_rate: Decimal | None
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    volume: int | None
    raw: dict[str, Any] = field(default_factory=dict)


def inquire_current_price(
    client: KisClient,
    *,
    market: str,
    symbol: str,
) -> CurrentPrice:
    normalized_market = normalize_market(market)
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol must not be empty")

    if normalized_market in DOMESTIC_MARKETS:
        payload = client.get(
            DOMESTIC_PRICE_PATH,
            tr_id=DOMESTIC_PRICE_TR_ID,
            params={
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": normalized_symbol,
            },
        )
        return parse_domestic_current_price(
            market=normalized_market,
            symbol=normalized_symbol,
            output=_output_dict(payload),
        )

    payload = client.get(
        OVERSEAS_PRICE_PATH,
        tr_id=OVERSEAS_PRICE_TR_ID,
        params={
            "AUTH": "",
            "EXCD": OVERSEAS_MARKET_CODES[normalized_market].upper(),
            "SYMB": normalized_symbol,
        },
    )
    return parse_overseas_current_price(
        market=normalized_market,
        symbol=normalized_symbol,
        output=_output_dict(payload),
    )


def parse_domestic_current_price(
    *,
    market: str,
    symbol: str,
    output: dict[str, Any],
) -> CurrentPrice:
    return CurrentPrice(
        market=market,
        symbol=symbol,
        name=str(output.get("hts_kor_isnm") or ""),
        price=_decimal(output.get("stck_prpr")),
        currency="KRW",
        change=_decimal(output.get("prdy_vrss")),
        change_rate=_decimal(output.get("prdy_ctrt")),
        open=_decimal(output.get("stck_oprc")),
        high=_decimal(output.get("stck_hgpr")),
        low=_decimal(output.get("stck_lwpr")),
        volume=_int(output.get("acml_vol")),
        raw=output,
    )


def parse_overseas_current_price(
    *,
    market: str,
    symbol: str,
    output: dict[str, Any],
) -> CurrentPrice:
    return CurrentPrice(
        market=market,
        symbol=symbol,
        name=str(output.get("name") or output.get("ename") or output.get("e_name") or ""),
        price=_decimal(output.get("last")),
        currency=str(output.get("curr") or output.get("currency") or ""),
        change=_decimal(output.get("diff") or output.get("t_xdif")),
        change_rate=_decimal(output.get("rate") or output.get("t_rate")),
        open=_decimal(output.get("open")),
        high=_decimal(output.get("high")),
        low=_decimal(output.get("low")),
        volume=_int(output.get("tvol") or output.get("volume")),
        raw=output,
    )


def _output_dict(payload: dict[str, Any]) -> dict[str, Any]:
    output = payload.get("output")
    if not isinstance(output, dict):
        raise ValueError("KIS response did not include output object")
    return output


def _decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    try:
        return int(Decimal(text))
    except (InvalidOperation, ValueError):
        return None
