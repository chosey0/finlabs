"""Kiwoom domestic industry APIs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from modules.brokers.kiwoom.endpoints.registry import lookup
from modules.brokers.kiwoom.models.industry import IndustryCode, IndustryIndex
from modules.brokers.kiwoom.parsers.rest import (
    parse_all_industry_index_rows,
    parse_industry_code_rows,
)

if TYPE_CHECKING:
    from modules.brokers.kiwoom.client import KiwoomClient

_ALL_INDEX_SPEC = lookup("domestic.industry.all_index")
_CODE_LIST_SPEC = lookup("domestic.industry.code_list")
_INDUSTRY_CODE_MARKET_TYPES = {"0", "1", "2", "4", "7"}


class DomesticIndustryAPI:
    """High-level Kiwoom domestic industry client."""

    def __init__(self, parent: "KiwoomClient") -> None:
        self._parent = parent

    async def all_index(
        self,
        industry_code: str,
        *,
        max_pages: int | None = None,
    ) -> list[IndustryIndex]:
        """Fetch all industry index rows from ``ka20003``.

        ``industry_code`` follows Kiwoom's request contract: ``001`` for KOSPI
        and ``101`` for KOSDAQ.
        """

        normalized_code = _normalize_industry_code(industry_code)
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        rows: dict[str, IndustryIndex] = {}
        cont_yn = "N"
        next_key = ""
        seen_next_keys: set[tuple[str, str]] = set()
        page_count = 0

        while max_pages is None or page_count < max_pages:
            response = await self._parent.request_raw(
                _ALL_INDEX_SPEC,
                json_body={"inds_cd": normalized_code},
                cont_yn=cont_yn,
                next_key=next_key,
            )
            page_count += 1
            for row in parse_all_industry_index_rows(
                response.payload,
                request_industry_code=normalized_code,
            ):
                rows[row.industry_code] = row

            next_cont_yn, next_key = _continuation(response.headers)
            if next_cont_yn != "Y" or not next_key:
                break
            cursor = (next_cont_yn, next_key)
            if cursor in seen_next_keys:
                break
            seen_next_keys.add(cursor)
            cont_yn = next_cont_yn

        return list(rows.values())

    async def code_list(
        self,
        market_type: str,
        *,
        max_pages: int | None = None,
    ) -> list[IndustryCode]:
        """Fetch industry code list rows from ``ka10101``.

        ``market_type`` follows Kiwoom's request contract: ``0`` KOSPI, ``1``
        KOSDAQ, ``2`` KOSPI200, ``4`` KOSPI100, and ``7`` KRX100.
        """

        normalized_market_type = _normalize_market_type(market_type)
        if max_pages is not None and max_pages < 1:
            raise ValueError("max_pages must be at least 1")

        rows: dict[tuple[str | None, str], IndustryCode] = {}
        cont_yn = "N"
        next_key = ""
        seen_next_keys: set[tuple[str, str]] = set()
        page_count = 0

        while max_pages is None or page_count < max_pages:
            response = await self._parent.request_raw(
                _CODE_LIST_SPEC,
                json_body={"mrkt_tp": normalized_market_type},
                cont_yn=cont_yn,
                next_key=next_key,
            )
            page_count += 1
            for row in parse_industry_code_rows(
                response.payload,
                request_market_type=normalized_market_type,
            ):
                rows[(row.market_code, row.code)] = row

            next_cont_yn, next_key = _continuation(response.headers)
            if next_cont_yn != "Y" or not next_key:
                break
            cursor = (next_cont_yn, next_key)
            if cursor in seen_next_keys:
                break
            seen_next_keys.add(cursor)
            cont_yn = next_cont_yn

        return list(rows.values())


def _normalize_industry_code(industry_code: str) -> str:
    normalized = industry_code.strip().upper()
    if not normalized:
        raise ValueError("industry_code must not be empty")
    return normalized


def _normalize_market_type(market_type: str) -> str:
    normalized = market_type.strip()
    if normalized not in _INDUSTRY_CODE_MARKET_TYPES:
        allowed = ", ".join(sorted(_INDUSTRY_CODE_MARKET_TYPES))
        raise ValueError(f"market_type must be one of: {allowed}")
    return normalized


def _continuation(headers: dict[str, str]) -> tuple[str, str]:
    normalized = {key.lower(): value for key, value in headers.items()}
    cont_yn = str(normalized.get("cont-yn") or "").strip().upper()
    next_key = str(normalized.get("next-key") or "").strip()
    return cont_yn, next_key
