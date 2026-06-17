from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from platformdirs import user_cache_dir


@dataclass(frozen=True)
class StoredToken:
    access_token: str
    token_type: str
    expires_at: datetime
    issued_at: datetime | None = None
    raw: dict[str, Any] | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return current >= self.expires_at


class JsonTokenStore:
    def __init__(self, path: Path, *, namespace: str = "") -> None:
        self.path = path
        self.namespace = namespace

    @classmethod
    def default(cls, *, namespace: str = "") -> "JsonTokenStore":
        return cls(
            Path(user_cache_dir("finlabs-cli", "finlabs")) / "tokens.json",
            namespace=namespace,
        )

    def namespaced(self, namespace: str) -> "JsonTokenStore":
        return JsonTokenStore(self.path, namespace=namespace)

    def get(self, key: str) -> StoredToken | None:
        payload = self._read()
        row = payload.get(self._key(key))
        if not isinstance(row, dict):
            return None
        return self._record_from_row(row)

    def _record_from_row(self, row: dict[str, Any]) -> StoredToken | None:
        if "expires_at" not in row:
            return None
        return StoredToken(
            access_token=str(row.get("access_token") or ""),
            token_type=str(row.get("token_type") or ""),
            expires_at=datetime.fromisoformat(str(row["expires_at"])),
            issued_at=_optional_datetime(row.get("issued_at")),
            raw=row.get("raw") if isinstance(row.get("raw"), dict) else None,
        )

    def set(self, key: str, record) -> None:
        payload = self._read()
        payload[self._key(key)] = {
            "access_token": record.access_token,
            "token_type": record.token_type,
            "expires_at": record.expires_at.isoformat(),
            "issued_at": getattr(record, "issued_at", None).isoformat()
            if getattr(record, "issued_at", None)
            else None,
            "raw": getattr(record, "raw", None),
        }
        self._write(payload)

    def delete(self, key: str) -> None:
        payload = self._read()
        payload.pop(self._key(key), None)
        self._write(payload)

    def records(self) -> dict[str, StoredToken]:
        records: dict[str, StoredToken] = {}
        prefix = f"{self.namespace}:" if self.namespace else ""
        for key, row in self._read().items():
            if prefix and not key.startswith(prefix):
                continue
            if not isinstance(row, dict):
                continue
            record = self._record_from_row(row)
            if record is not None:
                records[key.removeprefix(prefix)] = record
        return records

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}" if self.namespace else key

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("tokens.json must be a JSON object")
        return payload

    def _write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(self.path, 0o600)


def _optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(str(value))
