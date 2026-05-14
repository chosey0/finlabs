from __future__ import annotations

from kis.endpoints import overseas  # noqa: F401  (trigger spec registration)
from kis.endpoints.registry import EndpointSpec, lookup, names, register

__all__ = ["EndpointSpec", "lookup", "names", "register"]
