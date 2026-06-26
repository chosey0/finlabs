from __future__ import annotations

import os
from dataclasses import dataclass

from modules.brokers.krx.exceptions import KrxConfigError

DEFAULT_BASE_URL = "https://data-dbg.krx.co.kr"


@dataclass(frozen=True)
class Credentials:
    auth_key: str

    def __post_init__(self) -> None:
        if not self.auth_key.strip():
            raise KrxConfigError("auth_key must not be empty")

    @classmethod
    def from_env(cls, *, auth_key_var: str = "KRX_AUTH_KEY") -> "Credentials":
        auth_key = os.environ.get(auth_key_var)
        if not auth_key:
            raise KrxConfigError(f"{auth_key_var} must be set in environment")
        return cls(auth_key=auth_key)
