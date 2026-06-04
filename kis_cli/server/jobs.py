"""Transport-agnostic job orchestration core.

This module is deliberately free of FastAPI and of any ``kis_cli.services``
import. It provides only the in-memory infrastructure — a job record, a
thread-safe store, and a single-worker queue — so the same core can be driven
in-process (tests, a future scheduler) or wrapped by an HTTP transport.

The collection logic itself is injected as a ``runner`` callable. This keeps the
queue ignorant of *what* a job does, which is what makes it reusable and makes
the worker testable without real network or credentials.
"""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Callable, Optional


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


def _now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class Job:
    """A single on-demand collection request and its lifecycle state."""

    symbol: str
    interval: str
    start: str
    end: str | None = None
    count: int = 120
    adjusted: bool = True
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: JobStatus = JobStatus.PENDING
    market: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    finished_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


# A runner receives a Job and returns a result dict (e.g. fetched/stored/market).
JobRunner = Callable[[Job], dict[str, Any]]


class JobStore:
    """Thread-safe in-memory store of jobs.

    History lives only in process memory: on restart it is empty by design.
    The durable record of collected data is the DuckDB warehouse plus the
    app-DB ingest-run table written by the collection services.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}

    def add(self, job: Job) -> Job:
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        with self._lock:
            # Newest first for a sensible default ordering in clients.
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def update(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job


class JobQueue:
    """Single-worker FIFO queue that runs jobs one at a time, sequentially.

    A single worker is intentional: it serializes all warehouse writes through
    one path, which is the simplest way to avoid concurrent-writer contention on
    the embedded DuckDB file.
    """

    def __init__(
        self,
        runner: JobRunner,
        store: JobStore | None = None,
        error_sanitizer: Callable[[str], str] | None = None,
    ) -> None:
        self._runner = runner
        self.store = store or JobStore()
        # Injected so the core stays dependency-free; the HTTP-backed queue wires
        # the SDK's secret masker here (defense-in-depth on the error surface).
        self._sanitize_error = error_sanitizer or (lambda message: message)
        self._queue: queue.Queue[Optional[str]] = queue.Queue()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lifecycle_lock = threading.Lock()

    def start(self) -> None:
        # Guard start/stop so concurrent callers cannot spawn a second worker,
        # which would break the single-writer serialization the class guarantees.
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="kis-job-worker", daemon=True)
            self._thread.start()

    def stop(self, *, timeout: float | None = 5.0) -> None:
        with self._lifecycle_lock:
            self._stop.set()
            self._queue.put(None)  # unblock the worker so it can observe the stop flag
            if self._thread is not None:
                self._thread.join(timeout=timeout)
                self._thread = None

    def submit(self, job: Job) -> Job:
        self.store.add(job)
        self._queue.put(job.id)
        return job

    def join(self) -> None:
        """Block until all submitted jobs have been processed (test helper)."""
        self._queue.join()

    def _run(self) -> None:
        while not self._stop.is_set():
            job_id = self._queue.get()
            try:
                if job_id is None:
                    continue
                self._process(job_id)
            finally:
                self._queue.task_done()

    def _process(self, job_id: str) -> None:
        job = self.store.get(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.started_at = _now()
        self.store.update(job)
        try:
            # Collection (and thus auth.call_with_sdk_client / asyncio.run) runs
            # ONLY here on the worker thread — never inside a request coroutine.
            result = self._runner(job)
            job.result = result
            job.market = result.get("market", job.market)
            job.status = JobStatus.SUCCEEDED
        except Exception as exc:  # isolate failures so the next job still runs
            job.error = self._sanitize_error(str(exc))
            job.status = JobStatus.FAILED
        finally:
            job.finished_at = _now()
            self.store.update(job)
