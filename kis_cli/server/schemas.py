"""Pydantic request/response models for the job server HTTP surface."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from kis_cli.server.jobs import Job


class JobCreate(BaseModel):
    symbol: str = Field(..., description="Ticker symbol, e.g. NVDA.")
    interval: str = Field("1d", description="1d/1w/1mo for daily, or 1m/5m for minutes.")
    start: str = Field(..., description="Start date (YYYY-MM-DD) or minute start timestamp.")
    end: str | None = Field(None, description="End date for daily history; defaults to today.")
    count: int = Field(120, ge=1, description="Number of bars for minute collection.")
    adjusted: bool = Field(True, description="Use adjusted prices for daily history.")


class JobView(BaseModel):
    id: str
    symbol: str
    interval: str
    start: str
    end: str | None
    status: str
    market: str | None
    result: dict[str, Any] | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    @classmethod
    def from_job(cls, job: Job) -> "JobView":
        return cls(
            id=job.id,
            symbol=job.symbol,
            interval=job.interval,
            start=job.start,
            end=job.end,
            status=job.status.value,
            market=job.market,
            result=job.result,
            error=job.error,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )
