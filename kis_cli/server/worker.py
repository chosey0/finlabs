"""The collection runner: bridges a Job to ``kis_cli.services.chart``.

This is the only server module that imports the collection services and KIS
credentials path. It is invoked exclusively from the JobQueue worker thread,
which satisfies the ``asyncio.run`` constraint in
``kis_cli.services.auth.call_with_sdk_client`` (that helper creates a fresh event
loop and must not run inside an already-running loop).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from kis import mask_sensitive_message

from kis_cli.server.jobs import Job, JobQueue
from kis_cli.services.chart import collect_overseas_minutes, collect_ohlcv_history

# Daily intervals map to the collect_ohlcv_history `period` argument.
DAILY_INTERVAL_PERIODS: dict[str, str] = {"1d": "D", "1w": "W", "1mo": "M"}


def _parse_minute_interval(interval: str) -> int | None:
    normalized = interval.strip().lower()
    for suffix in ("m", "min", "minute", "minutes"):
        if normalized.endswith(suffix):
            head = normalized[: -len(suffix)].strip()
            if head.isdigit():
                return int(head)
    return None


def run_collection(
    job: Job,
    *,
    warehouse_path: Path | None = None,
    profile: str | None = None,
) -> dict[str, Any]:
    """Execute a collection job and return a result summary.

    Always passes ``save=True`` (and ``store="duckdb"`` for daily history). In the
    services layer the ingest-run audit tracking is inseparable from ``save=True``,
    so this is what makes both warehouse persistence and the durable audit record
    happen. Omitting it would silently persist nothing.
    """
    interval = job.interval.strip().lower()
    period = DAILY_INTERVAL_PERIODS.get(interval)
    if period is not None:
        result = collect_ohlcv_history(
            symbol=job.symbol,
            start=job.start,
            end=job.end,
            period=period,
            profile=profile,
            db_path=warehouse_path,
            save=True,
            store="duckdb",
            adjusted=job.adjusted,
        )
        return {"fetched": result.fetched, "stored": result.stored, "market": result.market}

    minutes = _parse_minute_interval(interval)
    if minutes is not None:
        result = collect_overseas_minutes(
            symbol=job.symbol,
            start=job.start,
            interval_minutes=minutes,
            count=job.count,
            profile=profile,
            db_path=warehouse_path,
            save=True,
        )
        return {"fetched": result.fetched, "stored": result.stored, "market": result.market}

    raise ValueError(
        f"unsupported interval '{job.interval}'; use one of "
        f"{', '.join(DAILY_INTERVAL_PERIODS)} or a minute interval like '1m'/'5m'"
    )


def build_job_queue(
    *,
    warehouse_path: Path | None = None,
    profile: str | None = None,
) -> JobQueue:
    """Wire a JobQueue with the real collection runner."""

    def runner(job: Job) -> dict[str, Any]:
        return run_collection(job, warehouse_path=warehouse_path, profile=profile)

    return JobQueue(runner=runner, error_sanitizer=mask_sensitive_message)
