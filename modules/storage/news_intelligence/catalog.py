"""Read KIS-derived domestic security snapshots for news discovery."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime

from modules.domain.news_intelligence import (
    KST,
    CatalogAlias,
    CatalogSecurity,
    CatalogSnapshot,
    HistoricalNameStatus,
)
from modules.storage.news_intelligence.database import connect, resolve_dsn


def load_catalog_snapshot(
    dsn: str | None = None,
    *,
    configured_aliases: dict[tuple[str, str], tuple[CatalogAlias, ...]] | None = None,
) -> CatalogSnapshot:
    aliases = configured_aliases or {}
    connection = connect(resolve_dsn(dsn))
    try:
        rows = connection.execute(
            """
            SELECT market, symbol, korean_name, english_name, security_type,
                   downloaded_at
            FROM domestic_symbols
            ORDER BY market, symbol
            """
        ).fetchall()
    finally:
        connection.close()
    if not rows:
        raise ValueError("domestic symbol catalog is empty")

    acquired_values = tuple(_parse_acquired_at(str(row[5])) for row in rows)
    acquired_at = max(acquired_values)
    securities: list[CatalogSecurity] = []
    canonical_rows: list[dict[str, str]] = []
    for market, symbol, korean_name, english_name, security_type, downloaded_at in rows:
        display_name = str(korean_name or english_name or symbol).strip()
        official_aliases = tuple(
            CatalogAlias(
                alias_id=f"catalog:{market}:{symbol}:{kind}",
                term=term,
                valid_from=date.min,
                valid_to=None,
                source="kis-domestic-symbol-master",
                historical_name_status=HistoricalNameStatus.CURRENT_ONLY,
            )
            for kind, term in (
                ("ko", str(korean_name or "").strip()),
                ("en", str(english_name or "").strip()),
            )
            if term
        )
        security = CatalogSecurity(
            security_id=f"{market}:{symbol}",
            market=str(market),
            symbol=str(symbol),
            display_name=display_name,
            aliases=official_aliases + aliases.get((str(market), str(symbol)), ()),
        )
        securities.append(security)
        canonical_rows.append(
            {
                "market": str(market),
                "symbol": str(symbol),
                "korean_name": str(korean_name or ""),
                "english_name": str(english_name or ""),
                "security_type": str(security_type or ""),
                "downloaded_at": str(downloaded_at),
            }
        )
    checksum = hashlib.sha256(
        json.dumps(
            canonical_rows,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return CatalogSnapshot(
        snapshot_id=f"kis-domestic:{checksum[:16]}",
        version="kis-domestic-catalog-v1",
        source="kis-domestic-symbol-master",
        acquired_at=acquired_at,
        checksum=checksum,
        securities=tuple(securities),
    )


def search_catalog(
    snapshot: CatalogSnapshot,
    query: str,
    *,
    limit: int = 20,
) -> tuple[CatalogSecurity, ...]:
    normalized = " ".join(query.split()).casefold()
    if not normalized:
        raise ValueError("catalog query must not be empty")
    if not 1 <= limit <= 100:
        raise ValueError("catalog limit must be between 1 and 100")
    matched = [
        security
        for security in snapshot.securities
        if normalized in security.symbol.casefold()
        or normalized in security.display_name.casefold()
        or any(normalized in alias.term.casefold() for alias in security.aliases)
    ]
    return tuple(
        sorted(
            matched,
            key=lambda item: (
                item.display_name.casefold() != normalized,
                item.market,
                item.symbol,
            ),
        )[:limit]
    )


def _parse_acquired_at(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return parsed.replace(tzinfo=KST)
    return parsed.astimezone(KST)
