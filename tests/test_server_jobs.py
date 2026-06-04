from __future__ import annotations

import threading

import pytest

from kis_cli.server import worker
from kis_cli.server.jobs import Job, JobQueue, JobStatus, JobStore


def _run_queue(runner, jobs):
    queue = JobQueue(runner=runner)
    queue.start()
    try:
        for job in jobs:
            queue.submit(job)
        queue.join()
    finally:
        queue.stop()
    return queue


def test_jobs_run_sequentially_and_record_status() -> None:
    order: list[str] = []

    def runner(job: Job) -> dict:
        order.append(job.symbol)
        return {"fetched": 1, "stored": 1, "market": "NASDAQ"}

    jobs = [Job(symbol=s, interval="1d", start="2024-01-01") for s in ("A", "B", "C")]
    queue = _run_queue(runner, jobs)

    assert order == ["A", "B", "C"]
    for job in jobs:
        stored = queue.store.get(job.id)
        assert stored is not None
        assert stored.status is JobStatus.SUCCEEDED
        assert stored.result == {"fetched": 1, "stored": 1, "market": "NASDAQ"}
        assert stored.market == "NASDAQ"
        assert stored.started_at is not None
        assert stored.finished_at is not None


def test_job_failure_is_isolated_and_recorded() -> None:
    def runner(job: Job) -> dict:
        if job.symbol == "BAD":
            raise ValueError("symbol 'BAD' not found in symbols table")
        return {"fetched": 2, "stored": 2, "market": "NASDAQ"}

    good1 = Job(symbol="GOOD1", interval="1d", start="2024-01-01")
    bad = Job(symbol="BAD", interval="1d", start="2024-01-01")
    good2 = Job(symbol="GOOD2", interval="1d", start="2024-01-01")
    queue = _run_queue(runner, [good1, bad, good2])

    assert queue.store.get(bad.id).status is JobStatus.FAILED
    assert "BAD" in queue.store.get(bad.id).error
    # Failure of one job must not stop the worker.
    assert queue.store.get(good1.id).status is JobStatus.SUCCEEDED
    assert queue.store.get(good2.id).status is JobStatus.SUCCEEDED


def test_fresh_store_is_empty_history_resets_on_restart() -> None:
    # AC9: in-memory job history does not survive a restart (a new store/queue).
    assert JobStore().list() == []
    queue = JobQueue(runner=lambda job: {})
    assert queue.store.list() == []


def test_run_collection_daily_passes_save_true(monkeypatch) -> None:
    captured: dict = {}

    class _Result:
        fetched = 5
        stored = 5
        market = "NASDAQ"

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr(worker, "collect_ohlcv_history", fake_collect)
    job = Job(symbol="NVDA", interval="1d", start="2024-01-01", end="2024-02-01")
    result = worker.run_collection(job, warehouse_path=None, profile="p")

    assert captured["save"] is True
    assert captured["store"] == "duckdb"
    assert captured["period"] == "D"
    assert captured["symbol"] == "NVDA"
    assert result == {"fetched": 5, "stored": 5, "market": "NASDAQ"}


def test_run_collection_minutes_passes_save_true(monkeypatch) -> None:
    captured: dict = {}

    class _Result:
        fetched = 3
        stored = 3
        market = "NASDAQ"

    def fake_collect(**kwargs):
        captured.update(kwargs)
        return _Result()

    monkeypatch.setattr(worker, "collect_overseas_minutes", fake_collect)
    job = Job(symbol="TSLA", interval="5m", start="2024-01-01 09:30:00", count=60)
    worker.run_collection(job)

    assert captured["save"] is True
    assert captured["interval_minutes"] == 5
    assert captured["count"] == 60


def test_error_is_sanitized_before_storage() -> None:
    # The HTTP-backed queue injects a sanitizer; ensure it is applied to job.error.
    def runner(job: Job) -> dict:
        raise RuntimeError("appsecret=SUPERSECRET leaked")

    queue = JobQueue(runner=runner, error_sanitizer=lambda m: m.replace("SUPERSECRET", "***"))
    queue.start()
    try:
        job = queue.submit(Job(symbol="A", interval="1d", start="2024-01-01"))
        queue.join()
    finally:
        queue.stop()
    stored = queue.store.get(job.id)
    assert stored.status is JobStatus.FAILED
    assert "SUPERSECRET" not in stored.error
    assert "***" in stored.error


def test_run_collection_rejects_unsupported_interval() -> None:
    job = Job(symbol="NVDA", interval="3y", start="2024-01-01")
    with pytest.raises(ValueError, match="unsupported interval"):
        worker.run_collection(job)


def test_collection_runs_on_worker_thread_not_caller() -> None:
    # The asyncio.run constraint requires collection off the request thread.
    caller_thread = threading.current_thread().name
    seen: dict = {}

    def runner(job: Job) -> dict:
        seen["thread"] = threading.current_thread().name
        return {}

    _run_queue(runner, [Job(symbol="A", interval="1d", start="2024-01-01")])
    assert seen["thread"] != caller_thread
    assert seen["thread"] == "kis-job-worker"
