from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ProductInfo:
    market: str
    symbol: str
    product_type: str
    name: str
    english_name: str
    standard_code: str
    short_code: str
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class FinancialSummary:
    market: str
    symbol: str
    fiscal_period: str
    revenue: Decimal | None
    operating_profit: Decimal | None
    net_income: Decimal | None
    roe: Decimal | None
    debt_ratio: Decimal | None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class DomesticVolumeRankItem:
    market: str
    symbol: str
    name: str
    rank: int | None
    price: Decimal | None
    change: Decimal | None
    change_rate: Decimal | None
    volume: int | None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class InvestorFlow:
    market: str
    symbol: str
    date: str
    close: Decimal | None
    foreign_net_buy_quantity: int | None
    individual_net_buy_quantity: int | None
    institution_net_buy_quantity: int | None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class OverseasVolumeSurgeItem:
    exchange: str
    symbol: str
    name: str
    price: Decimal | None
    change: Decimal | None
    change_rate: Decimal | None
    volume: int | None
    raw: dict[str, Any] | None = None
