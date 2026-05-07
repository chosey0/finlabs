from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.config.resolver import resolve_profile
from kis_cli.core.auth import KisAuthError, issue_access_token
from kis_cli.core.token_cache import CachedToken, read_cached_token, write_cached_token


@dataclass(frozen=True)
class AuthTestResult:
    profile_name: str
    profile_id: str
    environment: str
    token_status: str
    expires_at: str
    cache_path: Path


def get_rest_token(
    *,
    profile: str | None = None,
    config_path: Path | None = None,
    refresh: bool = False,
) -> tuple[CachedToken, str]:
    resolved = resolve_profile(profile=profile, config_path=config_path)
    if not refresh:
        cached = read_cached_token(profile_id=resolved.profile_id)
        if (
            cached is not None
            and cached.profile_name == resolved.name
            and cached.environment == resolved.environment
            and cached.is_valid()
        ):
            return cached, "reused"

    issued = issue_access_token(
        environment=resolved.environment,
        app_key=resolved.app_key,
        app_secret=resolved.app_secret,
    )
    cached = write_cached_token(
        issued,
        profile_id=resolved.profile_id,
        profile_name=resolved.name,
        environment=resolved.environment,
    )
    return cached, "issued"


def test_auth(
    *,
    profile: str | None = None,
    config_path: Path | None = None,
    refresh: bool = False,
) -> AuthTestResult:
    try:
        token, status = get_rest_token(
            profile=profile,
            config_path=config_path,
            refresh=refresh,
        )
    except KisAuthError:
        raise

    return AuthTestResult(
        profile_name=token.profile_name,
        profile_id=token.profile_id,
        environment=token.environment,
        token_status=status,
        expires_at=token.expires_at.isoformat(),
        cache_path=token.path,
    )
