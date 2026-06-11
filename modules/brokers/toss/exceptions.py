from __future__ import annotations

from typing import Any


class TossError(Exception):
    """Base exception for the Toss Securities Open API SDK."""


class TossConfigError(TossError):
    """Raised when SDK configuration is missing or invalid."""


class TossAuthError(TossError):
    """Raised when OAuth token issuance fails."""


class TossApiError(TossError):
    """Raised when the Open API returns an error response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        code: str | None = None,
        request_id: str | None = None,
        data: dict[str, Any] | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.request_id = request_id
        self.data = data
        self.retry_after = retry_after


class TossRateLimitError(TossApiError):
    """Raised when a request remains rate-limited after retries."""
