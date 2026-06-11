from __future__ import annotations

import os
from dataclasses import dataclass

from modules.brokers.toss.exceptions import TossConfigError

DEFAULT_BASE_URL = "https://openapi.tossinvest.com"


@dataclass(frozen=True)
class Credentials:
    client_id: str
    client_secret: str

    def __post_init__(self) -> None:
        if not self.client_id.strip():
            raise TossConfigError("client_id must not be empty")
        if not self.client_secret.strip():
            raise TossConfigError("client_secret must not be empty")

    @classmethod
    def from_env(
        cls,
        *,
        client_id_var: str = "TOSS_CLIENT_ID",
        client_secret_var: str = "TOSS_CLIENT_SECRET",
    ) -> "Credentials":
        client_id = os.environ.get(client_id_var)
        client_secret = os.environ.get(client_secret_var)
        if not client_id or not client_secret:
            raise TossConfigError(
                f"{client_id_var} and {client_secret_var} must be set in environment"
            )
        return cls(client_id=client_id, client_secret=client_secret)
