from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.storage.app_db import connect_app
from kis_cli.utils.time import now_kst_iso


@dataclass(frozen=True)
class IngestRunRecord:
    id: int
    kind: str
    market: str | None
    symbol: str | None
    started_at: str
    finished_at: str | None
    status: str
    rows_written: int
    error: str | None


def start_ingest_run(
    app_db_path: Path,
    *,
    kind: str,
    market: str | None = None,
    symbol: str | None = None,
) -> int:
    with connect_app(app_db_path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO ingest_runs (
                kind, market, symbol, started_at, status
            )
            VALUES (?, ?, ?, ?, 'running')
            """,
            [kind, market, symbol, now_kst_iso()],
        )
        return int(cursor.lastrowid)


def finish_ingest_run(
    app_db_path: Path,
    run_id: int,
    *,
    status: str,
    rows_written: int = 0,
    error: str | None = None,
) -> None:
    with connect_app(app_db_path) as connection:
        connection.execute(
            """
            UPDATE ingest_runs
            SET finished_at = ?, status = ?, rows_written = ?, error = ?
            WHERE id = ?
            """,
            [now_kst_iso(), status, rows_written, error, run_id],
        )


def record_api_log(
    app_db_path: Path,
    *,
    endpoint: str,
    tr_id: str | None = None,
    status_code: int | None = None,
    elapsed_ms: int | None = None,
    error: str | None = None,
) -> None:
    with connect_app(app_db_path) as connection:
        connection.execute(
            """
            INSERT INTO api_logs (
                endpoint, tr_id, status_code, requested_at, elapsed_ms, error
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [endpoint, tr_id, status_code, now_kst_iso(), elapsed_ms, error],
        )


def list_ingest_runs(app_db_path: Path, *, limit: int = 20) -> list[IngestRunRecord]:
    return find_ingest_runs(app_db_path, limit=limit)


def find_ingest_runs(
    app_db_path: Path,
    *,
    limit: int = 20,
    status: str | None = None,
    kind: str | None = None,
    market: str | None = None,
    symbol: str | None = None,
    since: str | None = None,
) -> list[IngestRunRecord]:
    where: list[str] = []
    params: list[object] = []
    if status:
        where.append("lower(status) = lower(?)")
        params.append(status)
    if kind:
        where.append("lower(kind) = lower(?)")
        params.append(kind)
    if market:
        where.append("lower(market) = lower(?)")
        params.append(market)
    if symbol:
        where.append("lower(symbol) = lower(?)")
        params.append(symbol)
    if since:
        where.append("started_at >= ?")
        params.append(since)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    with connect_app(app_db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT id, kind, market, symbol, started_at, finished_at, status, rows_written, error
            FROM ingest_runs
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [
        IngestRunRecord(
            id=row["id"],
            kind=row["kind"],
            market=row["market"],
            symbol=row["symbol"],
            started_at=row["started_at"],
            finished_at=row["finished_at"],
            status=row["status"],
            rows_written=row["rows_written"],
            error=row["error"],
        )
        for row in rows
    ]


def list_api_logs(app_db_path: Path, *, limit: int = 20) -> list[dict[str, object]]:
    return find_api_logs(app_db_path, limit=limit)


def find_api_logs(
    app_db_path: Path,
    *,
    limit: int = 20,
    endpoint: str | None = None,
    since: str | None = None,
) -> list[dict[str, object]]:
    where: list[str] = []
    params: list[object] = []
    if endpoint:
        where.append("lower(endpoint) LIKE lower(?)")
        params.append(f"%{endpoint}%")
    if since:
        where.append("requested_at >= ?")
        params.append(since)
    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    params.append(limit)
    with connect_app(app_db_path) as connection:
        rows = connection.execute(
            f"""
            SELECT endpoint, tr_id, status_code, requested_at, elapsed_ms, error
            FROM api_logs
            {where_sql}
            ORDER BY id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]
