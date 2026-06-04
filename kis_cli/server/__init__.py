"""kis_cli.server — localhost FastAPI job server for on-demand collection.

Layering:

- ``config``  : shared host/port constants used by server, CLI client, and dashboard.
- ``jobs``    : transport-agnostic job core (Job, JobStore, JobQueue). No FastAPI,
                no services imports — pure in-memory orchestration infrastructure.
- ``worker``  : the collection runner that bridges a Job to ``kis_cli.services.chart``.
- ``app``     : a thin FastAPI HTTP wrapper over ``jobs`` + ``worker``.

The job core is deliberately free of FastAPI so the same queue can be driven
in-process (tests, future schedulers) or over HTTP.
"""

from __future__ import annotations

from kis_cli.server.jobs import Job, JobQueue, JobStatus, JobStore

__all__ = ["Job", "JobQueue", "JobStatus", "JobStore"]
