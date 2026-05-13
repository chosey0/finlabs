from __future__ import annotations


class KisError(Exception):
    """Base class for all kis SDK errors."""


class KisConfigError(KisError):
    """Raised when credentials or environment configuration is invalid."""


class KisAuthError(KisError):
    """Raised when KIS authentication (REST token or WS approval key) fails."""


class KisApiError(KisError):
    """Raised when a KIS REST API call returns an unsuccessful response."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        rt_cd: str | None = None,
        msg_cd: str | None = None,
        msg1: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.rt_cd = rt_cd
        self.msg_cd = msg_cd
        self.msg1 = msg1


class MockNotSupportedError(KisError):
    """Raised when an endpoint without mock TR ID is invoked under environment='mock'."""

    def __init__(self, endpoint_name: str) -> None:
        super().__init__(
            f"endpoint '{endpoint_name}' does not support the mock environment"
        )
        self.endpoint_name = endpoint_name


class KisRealtimeError(KisError):
    """Raised on WebSocket connection, subscription, or frame parsing failures."""
