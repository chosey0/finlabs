"""Shared connection settings for the job server, CLI client, and dashboard.

A single source of truth for host/port prevents the server and its clients from
drifting onto different ports. Values can be overridden via environment variables
so a developer can relocate the server without code changes.
"""

from __future__ import annotations

import os

SERVER_HOST: str = os.environ.get("KIS_SERVER_HOST", "127.0.0.1")
SERVER_PORT: int = int(os.environ.get("KIS_SERVER_PORT", "8765"))


def base_url() -> str:
    """Return the base URL clients should use to reach the job server."""
    return f"http://{SERVER_HOST}:{SERVER_PORT}"
