"""Thin FastAPI HTTP wrapper over the job core.

This module owns the KIS credentials boundary: the collection runner (and thus
profile/token loading) lives in this server process. Dashboard and CLI clients
only speak HTTP and never load credentials themselves.

The worker thread is started/stopped via the app lifespan so jobs run only while
the server is up.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException

from kis_cli.server.jobs import Job, JobQueue
from kis_cli.server.schemas import JobCreate, JobView
from kis_cli.server.worker import build_job_queue


def create_app(
    *,
    warehouse_path: Path | None = None,
    profile: str | None = None,
    queue: JobQueue | None = None,
) -> FastAPI:
    """Build the FastAPI app.

    ``queue`` can be injected for tests; otherwise a real collection-backed queue
    is created. The worker thread starts on app startup and stops on shutdown.
    """
    job_queue = queue or build_job_queue(warehouse_path=warehouse_path, profile=profile)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        job_queue.start()
        try:
            yield
        finally:
            job_queue.stop()

    app = FastAPI(title="kis job server", lifespan=lifespan)
    app.state.job_queue = job_queue

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/jobs", response_model=JobView, status_code=201)
    def create_job(payload: JobCreate) -> JobView:
        job = Job(
            symbol=payload.symbol,
            interval=payload.interval,
            start=payload.start,
            end=payload.end,
            count=payload.count,
            adjusted=payload.adjusted,
        )
        job_queue.submit(job)
        return JobView.from_job(job)

    @app.get("/jobs", response_model=list[JobView])
    def list_jobs() -> list[JobView]:
        return [JobView.from_job(job) for job in job_queue.store.list()]

    @app.get("/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: str) -> JobView:
        job = job_queue.store.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"job '{job_id}' not found")
        return JobView.from_job(job)

    return app
