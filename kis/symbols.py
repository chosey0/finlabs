"""Symbol master download + parsing for KIS domestic and overseas listings.

The KIS-provided master files are static zip archives served over plain HTTPS:
no auth header or KIS REST flow involved. We therefore route this domain to
`httpx.get` rather than the auth'd transport in `kis._internal.http`.
"""

from __future__ import annotations

import csv
import zipfile
from datetime import UTC, datetime
from io import BytesIO, StringIO

import httpx

from kis.models.symbol import SymbolRecord

DOMESTIC_MARKETS = {"KOSPI", "KOSDAQ"}
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
SUPPORTED_SYMBOL_MARKETS = DOMESTIC_MARKETS | set(OVERSEAS_MARKET_CODES)
ALL_SYMBOL_MARKETS = (
    "KOSPI",
    "KOSDAQ",
    "NASDAQ",
    "NYSE",
    "AMEX",
    "SHANGHAI",
    "SHANGHAI_INDEX",
    "SHENZHEN",
    "SHENZHEN_INDEX",
    "TOKYO",
    "HONGKONG",
    "HANOI",
    "HOCHIMINH",
)

MASTER_BASE_URL = "https://new.real.download.dws.co.kr/common/master"
DOMESTIC_SUFFIX_LENGTHS = {"KOSPI": 227, "KOSDAQ": 221}
DOMESTIC_FILE_NAMES = {"KOSPI": "kospi_code.mst", "KOSDAQ": "kosdaq_code.mst"}

KOSPI_PART2_COLUMNS = [
    "group_code",
    "market_cap_size_code",
    "index_industry_large_code",
    "index_industry_middle_code",
    "index_industry_small_code",
    "manufacturing",
    "low_liquidity",
    "governance_index",
    "kospi200_sector",
    "kospi100",
    "kospi50",
    "krx",
    "etp",
    "elw_issued",
    "krx100",
    "krx_auto",
    "krx_semiconductor",
    "krx_bio",
    "krx_bank",
    "spac",
    "krx_energy_chemistry",
    "krx_steel",
    "short_term_overheated",
    "krx_media_telecom",
    "krx_construction",
    "non1",
    "krx_securities",
    "krx_shipbuilding",
    "krx_insurance",
    "krx_transport",
    "sri",
    "base_price",
    "regular_lot_size",
    "after_hours_lot_size",
    "trading_halt",
    "liquidation",
    "administrative_issue",
    "market_warning",
    "warning_notice",
    "unfaithful_disclosure",
    "backdoor_listing",
    "lock_type",
    "par_value_change",
    "capital_increase_type",
    "margin_rate",
    "credit_order_available",
    "credit_period",
    "previous_volume",
    "par_value",
    "listed_date",
    "listed_shares",
    "capital",
    "fiscal_month",
    "public_offering_price",
    "preferred_stock",
    "short_sale_overheated",
    "abnormal_surge",
    "krx300",
    "kospi",
    "revenue",
    "operating_profit",
    "ordinary_profit",
    "net_income",
    "roe",
    "base_year_month",
    "market_cap",
    "group_company_code",
    "credit_limit_exceeded",
    "collateral_loan_available",
    "stock_loan_available",
]
KOSDAQ_PART2_COLUMNS = [
    "security_group_code",
    "market_cap_size_code",
    "index_industry_large_code",
    "index_industry_middle_code",
    "index_industry_small_code",
    "venture_company",
    "low_liquidity",
    "krx",
    "etp_product_code",
    "krx100",
    "krx_auto",
    "krx_semiconductor",
    "krx_bio",
    "krx_bank",
    "spac",
    "krx_energy_chemistry",
    "krx_steel",
    "short_term_overheated",
    "krx_media_telecom",
    "krx_construction",
    "investment_caution_issue",
    "krx_securities",
    "krx_shipbuilding",
    "krx_insurance",
    "krx_transport",
    "kosdaq150",
    "base_price",
    "regular_lot_size",
    "after_hours_lot_size",
    "trading_halt",
    "liquidation",
    "administrative_issue",
    "market_warning",
    "warning_notice",
    "unfaithful_disclosure",
    "backdoor_listing",
    "lock_type",
    "par_value_change",
    "capital_increase_type",
    "margin_rate",
    "credit_order_available",
    "credit_period",
    "previous_volume",
    "par_value",
    "listed_date",
    "listed_shares_thousand",
    "capital",
    "fiscal_month",
    "public_offering_price",
    "preferred_stock",
    "short_sale_overheated",
    "abnormal_surge",
    "krx300",
    "revenue",
    "operating_profit",
    "ordinary_profit",
    "net_income",
    "roe",
    "base_year_month",
    "market_cap",
    "group_company_code",
    "credit_limit_exceeded",
    "collateral_loan_available",
    "stock_loan_available",
]
KOSPI_WIDTHS = [
    2,
    1,
    4,
    4,
    4,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    9,
    5,
    5,
    1,
    1,
    1,
    2,
    1,
    1,
    1,
    2,
    2,
    2,
    3,
    1,
    3,
    12,
    12,
    8,
    15,
    21,
    2,
    7,
    1,
    1,
    1,
    1,
    1,
    9,
    9,
    9,
    5,
    9,
    8,
    9,
    3,
    1,
    1,
    1,
]
KOSDAQ_WIDTHS = [
    2,
    1,
    4,
    4,
    4,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    1,
    9,
    5,
    5,
    1,
    1,
    1,
    2,
    1,
    1,
    1,
    2,
    2,
    2,
    3,
    1,
    3,
    12,
    12,
    8,
    15,
    21,
    2,
    7,
    1,
    1,
    1,
    1,
    9,
    9,
    9,
    5,
    9,
    8,
    9,
    3,
    1,
    1,
    1,
]
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

    if normalized in DOMESTIC_MARKETS:
        return parse_domestic_master(normalized, content)
    return parse_overseas_master(normalized, content)


def parse_domestic_master(market: str, content: str) -> list[SymbolRecord]:
    normalized = normalize_market(market)
    suffix_length = DOMESTIC_SUFFIX_LENGTHS[normalized]
    widths = KOSPI_WIDTHS if normalized == "KOSPI" else KOSDAQ_WIDTHS
    columns = KOSPI_PART2_COLUMNS if normalized == "KOSPI" else KOSDAQ_PART2_COLUMNS
    records: list[SymbolRecord] = []

    for line in content.splitlines():
        if not line.strip():
            continue
        part1 = line[:-suffix_length]
        part2 = line[-suffix_length:]
        raw = {
            "short_code": part1[0:9].strip(),
            "standard_code": part1[9:21].strip(),
            "korean_name": part1[21:].strip(),
            **_split_fixed_width(part2, widths, columns),
        }
        records.append(
            SymbolRecord(
                market=normalized,
                symbol=raw["short_code"],
                standard_code=raw["standard_code"],
                korean_name=raw["korean_name"],
                security_type=raw.get("group_code")
                or raw.get("security_group_code", ""),
                currency="KRW",
                exchange_name=normalized,
                country_code="KR",
                listed_date=raw.get("listed_date", ""),
                base_price=_to_int(raw.get("base_price", "")),
                lot_size=_to_int(raw.get("regular_lot_size", "")),
                raw_source=_master_file_name(normalized),
                raw=raw,
            )
        )

    return records


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
    if market == "KOSPI":
        return f"{MASTER_BASE_URL}/kospi_code.mst.zip"
    if market == "KOSDAQ":
        return f"{MASTER_BASE_URL}/kosdaq_code.mst.zip"
    return f"{MASTER_BASE_URL}/{OVERSEAS_MARKET_CODES[market]}mst.cod.zip"


def _master_file_name(market: str) -> str:
    if market in DOMESTIC_MARKETS:
        return DOMESTIC_FILE_NAMES[market]
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


def _split_fixed_width(
    text: str, widths: list[int], columns: list[str]
) -> dict[str, str]:
    values: dict[str, str] = {}
    offset = 0
    for width, column in zip(widths, columns, strict=True):
        values[column] = text[offset : offset + width].strip()
        offset += width
    return values


def _to_int(value: str) -> int | None:
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None
