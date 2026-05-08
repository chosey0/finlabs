from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from kis_cli.config.paths import default_config_file
from kis_cli.config.resolver import read_config, resolve_profile
from kis_cli.core.auth import KisAuthError, issue_access_token
from kis_cli.core.token_cache import (
    CachedToken,
    read_cached_token,
    token_cache_path,
    write_cached_token,
)

KST = ZoneInfo("Asia/Seoul")
KST_LABEL = "KST"


@dataclass(frozen=True)
class AuthTestResult:
    profile_name: str
    profile_id: str
    environment: str
    token_status: str
    expires_at: str
    cache_path: Path


@dataclass(frozen=True)
class AuthStatusResult:
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
        expires_at=format_kst(token.expires_at),
        cache_path=token.path,
    )


def get_auth_statuses(
    *,
    profile: str | None = None,
    all_profiles: bool = False,
    config_path: Path | None = None,
) -> list[AuthStatusResult]:
    if profile and all_profiles:
        raise ValueError("pass either --profile or --all, not both")

    path = (config_path or default_config_file()).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"config not found at {path}")

    active_profile, profiles = read_config(path)
    if all_profiles:
        selected_names = list(profiles)
    else:
        selected_name = profile or active_profile
        if not selected_name:
            raise ValueError("active_profile is missing; pass --profile explicitly")
        selected_names = [selected_name]

    statuses: list[AuthStatusResult] = []
    for name in selected_names:
        raw = profiles.get(name)
        if raw is None:
            raise ValueError(f"profile '{name}' not found in {path}")

        profile_id = raw.values.get("id", "")
        environment = raw.values.get("environment", "")
        if not profile_id:
            statuses.append(
                AuthStatusResult(
                    profile_name=name,
                    profile_id="-",
                    environment=environment or "-",
                    token_status="invalid",
                    expires_at="-",
                    cache_path=token_cache_path(name),
                )
            )
            continue

        statuses.append(_build_auth_status(name, profile_id, environment))

    return statuses


def _build_auth_status(
    profile_name: str,
    profile_id: str,
    environment: str,
) -> AuthStatusResult:
    path = token_cache_path(profile_id)
    if not path.exists():
        return AuthStatusResult(
            profile_name=profile_name,
            profile_id=profile_id,
            environment=environment or "-",
            token_status="none",
            expires_at="-",
            cache_path=path,
        )

    cached = read_cached_token(profile_id=profile_id)
    if cached is None:
        return AuthStatusResult(
            profile_name=profile_name,
            profile_id=profile_id,
            environment=environment or "-",
            token_status="invalid",
            expires_at="-",
            cache_path=path,
        )

    now = datetime.now(UTC)
    status = "valid" if cached.is_valid(now=now) else "expired"
    if cached.profile_name != profile_name or cached.environment != environment:
        status = "invalid"

    return AuthStatusResult(
        profile_name=profile_name,
        profile_id=profile_id,
        environment=environment or cached.environment,
        token_status=status,
        expires_at=format_kst(cached.expires_at),
        cache_path=path,
    )


def format_kst(value: datetime) -> str:
    return f"{value.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')} {KST_LABEL}"
