from __future__ import annotations

from typing import Any


class KrxError(Exception):
    """Base exception for the KRX Data Marketplace Open API SDK."""


class KrxConfigError(KrxError):
    """Raised when SDK configuration is missing or invalid."""


class KrxApiError(KrxError):
    """Raised when the KRX Open API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.data = data
