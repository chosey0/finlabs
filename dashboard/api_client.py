"""HTTP client for the job server — used ONLY by the collect page.

Read pages must not import this module; they read the warehouse directly via
``dashboard.reader``. Keeping the HTTP client out of the read path is what
enforces the read/write separation at the import level.
"""

from __future__ import annotations

import httpx

from kis_cli.server.config import base_url


class JobServerClient:
    def __init__(self, base: str | None = None, timeout: float = 10.0) -> None:
        self._base = base or base_url()
        self._timeout = timeout

    def health(self) -> bool:
        try:
            with httpx.Client(base_url=self._base, timeout=self._timeout) as client:
                return client.get("/health").status_code == 200
        except httpx.HTTPError:
            return False

    def submit(self, payload: dict) -> dict:
        with httpx.Client(base_url=self._base, timeout=self._timeout) as client:
            response = client.post("/jobs", json=payload)
            response.raise_for_status()
            return response.json()

    def get(self, job_id: str) -> dict:
        with httpx.Client(base_url=self._base, timeout=self._timeout) as client:
            response = client.get(f"/jobs/{job_id}")
            response.raise_for_status()
            return response.json()

    def list(self) -> list[dict]:
        with httpx.Client(base_url=self._base, timeout=self._timeout) as client:
            response = client.get("/jobs")
            response.raise_for_status()
            return response.json()
