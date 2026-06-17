"""Symbol master download and parsing for KIS domestic and overseas listings.

The KIS-provided master files are static zip archives served over HTTPS. No auth
header or KIS REST flow is involved, so this domain is routed to
`httpx.get` rather than the auth'd transport in `kis._internal.http`.
"""

from __future__ import annotations

import csv
import zipfile
from dataclasses import dataclass
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
DOMESTIC_MARKET_FILES = {
    "KOSPI": "kospi_code.mst",
    "KOSDAQ": "kosdaq_code.mst",
}
SUPPORTED_SYMBOL_MARKETS = set(DOMESTIC_MARKET_FILES) | set(OVERSEAS_MARKET_CODES)
ALL_SYMBOL_MARKETS = (*DOMESTIC_MARKET_FILES, *OVERSEAS_MARKET_CODES)

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

KOSPI_WIDTHS = (
    2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1,
    1, 2, 2, 2, 3, 1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 1, 9,
    9, 9, 5, 9, 8, 9, 3, 1, 1, 1,
)
KOSPI_COLUMNS = (
    "group_code",
    "market_cap_size",
    "index_industry_large",
    "index_industry_medium",
    "index_industry_small",
    "manufacturing",
    "low_liquidity",
    "governance_index",
    "kospi200_sector",
    "kospi100",
    "kospi50",
    "krx",
    "etp",
    "elw_issuer",
    "krx100",
    "krx_auto",
    "krx_semiconductor",
    "krx_bio",
    "krx_bank",
    "spac",
    "krx_energy_chemical",
    "krx_steel",
    "short_term_overheat",
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
    "liquidation_trading",
    "management_stock",
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
    "ipo_price",
    "preferred_stock",
    "short_sale_overheat",
    "abnormal_surge",
    "krx300",
    "kospi",
    "revenue",
    "operating_profit",
    "ordinary_profit",
    "net_income",
    "roe",
    "reference_month",
    "market_cap",
    "group_company_code",
    "company_credit_limit_exceeded",
    "collateral_loan_available",
    "stock_lending_available",
)
KOSDAQ_WIDTHS = (
    2, 1, 4, 4, 4, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 1, 1, 1, 9, 5, 5, 1, 1, 1, 2, 1, 1, 1, 2, 2, 2, 3,
    1, 3, 12, 12, 8, 15, 21, 2, 7, 1, 1, 1, 1, 9, 9, 9, 5, 9, 8, 9,
    3, 1, 1, 1,
)
KOSDAQ_COLUMNS = (
    "security_group_code",
    "market_cap_size",
    "index_industry_large",
    "index_industry_medium",
    "index_industry_small",
    "venture",
    "low_liquidity",
    "krx",
    "etp_product_type",
    "krx100",
    "krx_auto",
    "krx_semiconductor",
    "krx_bio",
    "krx_bank",
    "spac",
    "krx_energy_chemical",
    "krx_steel",
    "short_term_overheat",
    "krx_media_telecom",
    "krx_construction",
    "investment_caution",
    "krx_securities",
    "krx_shipbuilding",
    "krx_insurance",
    "krx_transport",
    "kosdaq150",
    "base_price",
    "regular_lot_size",
    "after_hours_lot_size",
    "trading_halt",
    "liquidation_trading",
    "management_stock",
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
    "ipo_price",
    "preferred_stock",
    "short_sale_overheat",
    "abnormal_surge",
    "krx300",
    "revenue",
    "operating_profit",
    "ordinary_profit",
    "net_income",
    "roe",
    "reference_month",
    "market_cap",
    "group_company_code",
    "company_credit_limit_exceeded",
    "collateral_loan_available",
    "stock_lending_available",
)


@dataclass(frozen=True)
class DomesticMasterSpec:
    widths: tuple[int, ...]
    columns: tuple[str, ...]
    security_type_field: str


DOMESTIC_MASTER_SPECS = {
    "KOSPI": DomesticMasterSpec(
        widths=KOSPI_WIDTHS,
        columns=KOSPI_COLUMNS,
        security_type_field="group_code",
    ),
    "KOSDAQ": DomesticMasterSpec(
        widths=KOSDAQ_WIDTHS,
        columns=KOSDAQ_COLUMNS,
        security_type_field="security_group_code",
    ),
}


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

    if normalized in DOMESTIC_MASTER_SPECS:
        return parse_domestic_master(normalized, content)
    return parse_overseas_master(normalized, content)


def parse_domestic_master(market: str, content: str) -> list[SymbolRecord]:
    normalized = normalize_market(market)
    try:
        spec = DOMESTIC_MASTER_SPECS[normalized]
    except KeyError as exc:
        raise ValueError(f"domestic master is not available for: {normalized}") from exc

    suffix_width = sum(spec.widths)
    records: list[SymbolRecord] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        if not line.strip():
            continue
        if len(line) < 21 + suffix_width:
            raise ValueError(
                f"invalid {normalized} master row {line_number}: "
                f"expected at least {21 + suffix_width} characters, got {len(line)}"
            )

        prefix_end = len(line) - suffix_width
        prefix = line[:prefix_end]
        fixed_values = _parse_fixed_width(line[prefix_end:], spec)
        raw = {
            "short_code": prefix[:9].strip(),
            "standard_code": prefix[9:21].strip(),
            "korean_name": prefix[21:].strip(),
            **fixed_values,
        }
        records.append(
            SymbolRecord(
                market=normalized,
                symbol=raw["short_code"],
                standard_code=raw["standard_code"],
                realtime_symbol=raw["short_code"],
                korean_name=raw["korean_name"],
                security_type=raw[spec.security_type_field],
                currency="KRW",
                exchange_id=normalized,
                exchange_code="KRX",
                exchange_name="Korea Exchange",
                country_code="KR",
                listed_date=raw["listed_date"],
                base_price=_to_int(raw["base_price"]),
                lot_size=_to_int(raw["regular_lot_size"]),
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
    if market in DOMESTIC_MARKET_FILES:
        return f"{MASTER_BASE_URL}/{DOMESTIC_MARKET_FILES[market]}.zip"
    return f"{MASTER_BASE_URL}/{OVERSEAS_MARKET_CODES[market]}mst.cod.zip"


def _master_file_name(market: str) -> str:
    if market in DOMESTIC_MARKET_FILES:
        return DOMESTIC_MARKET_FILES[market]
    return f"{OVERSEAS_MARKET_CODES[market]}mst.cod"


def _parse_fixed_width(content: str, spec: DomesticMasterSpec) -> dict[str, str]:
    if len(spec.widths) != len(spec.columns):
        raise RuntimeError("domestic master widths and columns must have equal lengths")
    raw: dict[str, str] = {}
    offset = 0
    for column, width in zip(spec.columns, spec.widths, strict=True):
        raw[column] = content[offset : offset + width].strip()
        offset += width
    return raw


def _download_zip(url: str, *, timeout_seconds: float) -> bytes:
    response = httpx.get(
        url,
        headers={"User-Agent": "finlabs-kis-sdk/0.1.0"},
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
