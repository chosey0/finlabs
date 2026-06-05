"""Symbol master download + parsing for KIS overseas listings.

The KIS-provided overseas master files are static zip archives served over plain HTTPS:
no auth header or KIS REST flow involved. We therefore route this domain to
`httpx.get` rather than the auth'd transport in `kis._internal.http`.
"""

from __future__ import annotations

import csv
import zipfile
from datetime import UTC, datetime
from io import BytesIO, StringIO

import httpx

from modules.brokers.kis.models.symbol import SymbolRecord

OVERSEAS_MARKET_CODES = {
    "NASDAQ": "nas",
    "NYSE": "nys",
    "AMEX": "ams",
    "SHANGHAI": "shs",
    "SHANGHAI_INDEX": "shi",
    "SHENZHEN": "szs",
    "SHENZHEN_INDEX": "szi",
    "TOKYO": "tse",
    "HONGKONG": "hks",
    "HANOI": "hnx",
    "HOCHIMINH": "hsx",
}
SUPPORTED_SYMBOL_MARKETS = set(OVERSEAS_MARKET_CODES)
ALL_SYMBOL_MARKETS = tuple(OVERSEAS_MARKET_CODES)

MASTER_BASE_URL = "https://new.real.download.dws.co.kr/common/master"
OVERSEAS_COLUMNS = [
    "national_code",
    "exchange_id",
    "exchange_code",
    "exchange_name",
    "symbol",
    "realtime_symbol",
    "korean_name",
    "english_name",
    "security_type",
    "currency",
    "float_position",
    "data_type",
    "base_price",
    "bid_order_size",
    "ask_order_size",
    "market_start_time",
    "market_end_time",
    "dr_yn",
    "dr_country_code",
    "industry_code",
    "has_index_constituents",
    "tick_size_type",
    "classification_code",
    "tick_size_type_detail",
]


def normalize_market(market: str) -> str:
    normalized = market.strip().upper().replace("-", "_")
    if normalized not in SUPPORTED_SYMBOL_MARKETS:
        allowed = ", ".join(ALL_SYMBOL_MARKETS)
        raise ValueError(f"market must be one of: {allowed}")
    return normalized


def download_symbol_master(
    market: str,
    *,
    downloaded_at: str | None = None,
    timeout_seconds: float = 30.0,
) -> list[SymbolRecord]:
    """Download and parse the KIS-published master file for a market.

    `downloaded_at` is recorded on every returned SymbolRecord. When omitted,
    UTC ISO 8601 is used; cli/services that prefer KST should pass their own
    formatted value.
    """
    normalized = normalize_market(market)
    data = _download_zip(_master_url(normalized), timeout_seconds=timeout_seconds)
    records = parse_symbol_master(normalized, data)
    stamp = downloaded_at or datetime.now(UTC).isoformat()
    return [record.with_downloaded_at(stamp) for record in records]


def parse_symbol_master(market: str, zip_bytes: bytes) -> list[SymbolRecord]:
    normalized = normalize_market(market)
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        member = _find_member(archive, _master_file_name(normalized))
        content = archive.read(member).decode("cp949")

    return parse_overseas_master(normalized, content)


def parse_overseas_master(market: str, content: str) -> list[SymbolRecord]:
    normalized = normalize_market(market)
    rows = csv.reader(StringIO(content), delimiter="\t")
    records: list[SymbolRecord] = []

    for values in rows:
        if not values or not any(value.strip() for value in values):
            continue
        padded = values + [""] * (len(OVERSEAS_COLUMNS) - len(values))
        raw = {
            column: padded[index].strip()
            for index, column in enumerate(OVERSEAS_COLUMNS)
        }
        records.append(
            SymbolRecord(
                market=normalized,
                symbol=raw["symbol"],
                realtime_symbol=raw["realtime_symbol"],
                korean_name=raw["korean_name"],
                english_name=raw["english_name"],
                security_type=raw["security_type"],
                currency=raw["currency"],
                exchange_id=raw["exchange_id"],
                exchange_code=raw["exchange_code"],
                exchange_name=raw["exchange_name"],
                country_code=raw["national_code"],
                base_price=_to_int(raw["base_price"]),
                lot_size=_to_int(raw["bid_order_size"]),
                raw_source=_master_file_name(normalized),
                raw=raw,
            )
        )

    return records


def _master_url(market: str) -> str:
    return f"{MASTER_BASE_URL}/{OVERSEAS_MARKET_CODES[market]}mst.cod.zip"


def _master_file_name(market: str) -> str:
    return f"{OVERSEAS_MARKET_CODES[market]}mst.cod"


def _download_zip(url: str, *, timeout_seconds: float) -> bytes:
    response = httpx.get(
        url,
        headers={"User-Agent": "kis-cli/0.1.0"},
        timeout=timeout_seconds,
        follow_redirects=True,
    )
    response.raise_for_status()
    return response.content


def _find_member(archive: zipfile.ZipFile, expected_name: str) -> str:
    names = archive.namelist()
    expected_lower = expected_name.lower()
    for name in names:
        if name.rsplit("/", 1)[-1].lower() == expected_lower:
            return name
    joined = ", ".join(names)
    raise ValueError(f"master file '{expected_name}' not found in archive: {joined}")


def _to_int(value: str) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None
