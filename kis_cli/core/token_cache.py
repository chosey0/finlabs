from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from secrets import token_hex
from typing import Any

from kis_cli.config.init import _chmod_owner_read_write
from kis_cli.config.paths import cache_dir
from modules.brokers.kis import IssuedToken

TOKEN_REFRESH_MARGIN = timedelta(minutes=5)


@dataclass(frozen=True)
class CachedToken:
    profile_id: str
    profile_name: str
    environment: str
    access_token: str
    token_type: str
    issued_at: datetime
    expires_at: datetime
    path: Path

    def is_valid(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(UTC)
        return self.expires_at > current + TOKEN_REFRESH_MARGIN


@dataclass(frozen=True)
class TokenCacheReadResult:
    status: str
    path: Path
    token: CachedToken | None = None


def token_cache_path(profile_id: str) -> Path:
    return cache_dir() / "tokens" / f"{profile_id}.json"


def read_cached_token(*, profile_id: str) -> CachedToken | None:
    return read_cached_token_result(profile_id=profile_id).token


def read_cached_token_result(*, profile_id: str) -> TokenCacheReadResult:
    path = token_cache_path(profile_id)
    if not path.exists():
        return TokenCacheReadResult(status="missing", path=path)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        token = CachedToken(
            profile_id=str(data["profile_id"]),
            profile_name=str(data["profile_name"]),
            environment=str(data["environment"]),
            access_token=str(data["access_token"]),
            token_type=str(data.get("token_type") or "Bearer"),
            issued_at=_parse_datetime(str(data["issued_at"])),
            expires_at=_parse_datetime(str(data["expires_at"])),
            path=path,
        )
        return TokenCacheReadResult(status="ok", path=path, token=token)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return TokenCacheReadResult(status="invalid", path=path)


def write_cached_token(
    token: IssuedToken,
    *,
    profile_id: str,
    profile_name: str,
    environment: str,
) -> CachedToken:
    path = token_cache_path(profile_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {
        "profile_id": profile_id,
        "profile_name": profile_name,
        "environment": environment,
        "access_token": token.access_token,
        "token_type": token.token_type,
        "issued_at": token.issued_at.astimezone(UTC).isoformat(),
        "expires_at": token.expires_at.astimezone(UTC).isoformat(),
    }
    content = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(f".{path.name}.{token_hex(8)}.tmp")
    tmp_path.write_text(content, encoding="utf-8")
    _chmod_owner_read_write(tmp_path)
    tmp_path.replace(path)
    _chmod_owner_read_write(path)
    return CachedToken(
        profile_id=profile_id,
        profile_name=profile_name,
        environment=environment,
        access_token=token.access_token,
        token_type=token.token_type,
        issued_at=token.issued_at.astimezone(UTC),
        expires_at=token.expires_at.astimezone(UTC),
        path=path,
    )


def clear_cached_token(*, profile_id: str) -> bool:
    path = token_cache_path(profile_id)
    if not path.exists():
        return False
    path.unlink()
    return True


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
