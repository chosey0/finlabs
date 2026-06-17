"""Dashboard-local runtime settings."""

from __future__ import annotations

import os

SERVER_HOST = os.getenv("FINLABS_JOB_SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("FINLABS_JOB_SERVER_PORT", "8765"))


def base_url() -> str:
    return f"http://{SERVER_HOST}:{SERVER_PORT}"
