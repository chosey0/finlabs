from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.core.symbol_master import download_symbol_master, normalize_market, record_to_db_values
from kis_cli.storage import connect, init_database
from kis_cli.storage.app_repositories import finish_ingest_run, record_api_log, start_ingest_run
from kis_cli.storage.repositories import search_symbols, upsert_symbols


@dataclass(frozen=True)
class SymbolDownloadResult:
    db_path: Path
    market: str
    downloaded: int
    stored: int


def download_and_store_symbols(*, market: str, db_path: Path | None = None) -> SymbolDownloadResult:
    normalized = normalize_market(market)
    init_result = init_database(db_path)
    run_id = start_ingest_run(
        init_result.app_path,
        kind="symbols",
        market=normalized,
    )
    try:
        records = download_symbol_master(normalized)
        with connect(init_result.path) as connection:
            stored = upsert_symbols(connection, (record_to_db_values(record) for record in records))
    except Exception as exc:
        message = str(exc)
        finish_ingest_run(
            init_result.app_path,
            run_id,
            status="failed",
            error=message,
        )
        record_api_log(
            init_result.app_path,
            endpoint=f"symbol_master:{normalized}",
            error=message,
        )
        raise

    finish_ingest_run(
        init_result.app_path,
        run_id,
        status="success",
        rows_written=stored,
    )
    record_api_log(
        init_result.app_path,
        endpoint=f"symbol_master:{normalized}",
        status_code=200,
    )
    return SymbolDownloadResult(
        db_path=init_result.path,
        market=normalized,
        downloaded=len(records),
        stored=stored,
    )


def search_stored_symbols(
    *,
    query: str,
    market: str | None = None,
    db_path: Path | None = None,
    limit: int = 20,
):
    normalized_market = normalize_market(market) if market else None
    with connect(db_path) as connection:
        return search_symbols(
            connection,
            query=query,
            market=normalized_market,
            limit=limit,
        )
