from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.core.symbol_master import download_symbol_master, normalize_market, record_to_db_values
from kis_cli.storage import (
    connect,
    connect_supabase,
    default_app_database_file,
    init_app_database,
    init_database,
    upsert_supabase_symbols,
)
from kis_cli.storage.app_repositories import finish_ingest_run, record_api_log, start_ingest_run
from kis_cli.storage.repositories import search_symbols, upsert_symbols


@dataclass(frozen=True)
class SymbolDownloadResult:
    db_path: Path | None
    market: str
    downloaded: int
    stored: int
    store: str = "duckdb"


def download_and_store_symbols(
    *,
    market: str,
    db_path: Path | None = None,
    store: str = "duckdb",
    supabase_dsn: str | None = None,
) -> SymbolDownloadResult:
    normalized = normalize_market(market)
    normalized_store = _normalize_store(store)
    if normalized_store == "supabase" and db_path is not None:
        raise ValueError("--db-path is only valid with --store duckdb")

    init_result = init_database(db_path) if normalized_store == "duckdb" else None
    app_path = init_result.app_path if init_result else init_app_database(default_app_database_file())
    run_id = start_ingest_run(
        app_path,
        kind="symbols",
        market=normalized,
    )
    try:
        records = download_symbol_master(normalized)
        values = [record_to_db_values(record) for record in records]
        if normalized_store == "supabase":
            with connect_supabase(dsn=supabase_dsn) as connection:
                stored = upsert_supabase_symbols(connection, values)
        else:
            with connect(init_result.path) as connection:
                stored = upsert_symbols(connection, values)
    except Exception as exc:
        message = str(exc)
        finish_ingest_run(
            app_path,
            run_id,
            status="failed",
            error=message,
        )
        record_api_log(
            app_path,
            endpoint=f"symbol_master:{normalized}",
            error=message,
        )
        raise

    finish_ingest_run(
        app_path,
        run_id,
        status="success",
        rows_written=stored,
    )
    record_api_log(
        app_path,
        endpoint=f"symbol_master:{normalized}",
        status_code=200,
    )
    return SymbolDownloadResult(
        db_path=init_result.path if init_result else None,
        market=normalized,
        downloaded=len(records),
        stored=stored,
        store=normalized_store,
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


def _normalize_store(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in {"duckdb", "supabase"}:
        raise ValueError("store must be one of: duckdb, supabase")
    return normalized
