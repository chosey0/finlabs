from __future__ import annotations


class KiwoomError(Exception):
    """Base class for all Kiwoom SDK errors."""


class KiwoomConfigError(KiwoomError):
    """Raised when credentials or environment configuration is invalid."""


class KiwoomAuthError(KiwoomError):
    """Raised when Kiwoom authentication fails."""


class KiwoomApiError(KiwoomError):
    """Raised when a Kiwoom REST API call returns an unsuccessful response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        return_code: str | None = None,
        return_msg: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.return_code = return_code
        self.return_msg = return_msg


class KiwoomRealtimeError(KiwoomError):
    """Raised on WebSocket connection, subscription, or frame parsing failures."""
