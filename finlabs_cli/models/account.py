from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal
from uuid import uuid4

BrokerName = Literal["kis", "kiwoom", "toss"]


@dataclass(frozen=True)
class Account:
    id: str
    alias: str
    broker: BrokerName
    owner_name: str
    environment: str
    expires_at: str
    account_number: str = ""
    account_password: str = ""
    credentials: dict[str, str] | None = None

    def __post_init__(self) -> None:
        if not self.alias.strip():
            raise ValueError("account alias must not be empty")
        if self.broker not in {"kis", "kiwoom", "toss"}:
            raise ValueError("broker must be one of: kis, kiwoom, toss")
        if self.credentials is None:
            object.__setattr__(self, "credentials", {})

    @classmethod
    def from_dict(cls, row: dict) -> "Account":
        return cls(
            id=str(row.get("id") or new_account_id()),
            alias=str(row["alias"]),
            broker=str(row["broker"]),  # type: ignore[arg-type]
            owner_name=str(row.get("owner_name") or ""),
            environment=str(row.get("environment") or "real"),
            expires_at=str(row.get("expires_at") or ""),
            account_number=str(row.get("account_number") or ""),
            account_password=str(row.get("account_password") or ""),
            credentials={
                str(key): str(value)
                for key, value in dict(row.get("credentials") or {}).items()
            },
        )

    def with_changes(self, **changes) -> "Account":
        return replace(self, **changes)

    def with_credential(self, key: str, value: str) -> "Account":
        credentials = dict(self.credentials or {})
        credentials[key] = value
        return replace(self, credentials=credentials)


def new_account_id() -> str:
    return str(uuid4())
