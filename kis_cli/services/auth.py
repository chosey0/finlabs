from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from kis_cli.config.paths import default_config_file
from kis_cli.config.resolver import read_config, resolve_profile
from kis_cli.core.auth import KisAuthError, issue_access_token
from kis_cli.core.client import KisClient
from kis_cli.core.token_cache import (
    CachedToken,
    clear_cached_token,
    read_cached_token,
    read_cached_token_result,
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
    expires_in: str
    cache_path: Path


@dataclass(frozen=True)
class AuthClearResult:
    profile_name: str
    profile_id: str
    environment: str
    cache_path: Path
    removed: bool


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


def build_rest_client(
    *,
    profile: str | None = None,
    config_path: Path | None = None,
    refresh: bool = False,
) -> KisClient:
    resolved = resolve_profile(profile=profile, config_path=config_path)
    token, _ = get_rest_token(profile=profile, config_path=config_path, refresh=refresh)
    return KisClient(profile=resolved, token=token)


def call_with_token_refresh_retry(
    operation,
    *,
    profile: str | None = None,
    config_path: Path | None = None,
):
    client = build_rest_client(profile=profile, config_path=config_path)
    try:
        return operation(client)
    except KisAuthError:
        refreshed_client = build_rest_client(
            profile=profile,
            config_path=config_path,
            refresh=True,
        )
        return operation(refreshed_client)


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
                    expires_in="-",
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
            expires_in="-",
            cache_path=path,
        )

    read_result = read_cached_token_result(profile_id=profile_id)
    if read_result.status == "invalid" or read_result.token is None:
        return AuthStatusResult(
            profile_name=profile_name,
            profile_id=profile_id,
            environment=environment or "-",
            token_status="invalid",
            expires_at="-",
            expires_in="-",
            cache_path=path,
        )

    cached = read_result.token
    now = datetime.now(UTC)
    status = _token_status(cached, now=now)
    if cached.profile_name != profile_name or cached.environment != environment:
        status = "invalid"

    return AuthStatusResult(
        profile_name=profile_name,
        profile_id=profile_id,
        environment=environment or cached.environment,
        token_status=status,
        expires_at=format_kst(cached.expires_at),
        expires_in=format_remaining(cached.expires_at, now=now) if status != "invalid" else "-",
        cache_path=path,
    )


def clear_auth_tokens(
    *,
    profile: str | None = None,
    all_profiles: bool = False,
    config_path: Path | None = None,
) -> list[AuthClearResult]:
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

    results: list[AuthClearResult] = []
    for name in selected_names:
        raw = profiles.get(name)
        if raw is None:
            raise ValueError(f"profile '{name}' not found in {path}")
        profile_id = raw.values.get("id", "")
        environment = raw.values.get("environment", "")
        cache_path = token_cache_path(profile_id or name)
        removed = clear_cached_token(profile_id=profile_id) if profile_id else False
        results.append(
            AuthClearResult(
                profile_name=name,
                profile_id=profile_id or "-",
                environment=environment or "-",
                cache_path=cache_path,
                removed=removed,
            )
        )

    return results


def format_kst(value: datetime) -> str:
    return f"{value.astimezone(KST).strftime('%Y-%m-%d %H:%M:%S')} {KST_LABEL}"


def format_remaining(expires_at: datetime, *, now: datetime | None = None) -> str:
    current = now or datetime.now(UTC)
    seconds = int((expires_at - current).total_seconds())
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    if days:
        return f"{sign}{days}d {hours}h {minutes}m"
    if hours:
        return f"{sign}{hours}h {minutes}m"
    return f"{sign}{minutes}m"


def _token_status(token: CachedToken, *, now: datetime) -> str:
    if token.expires_at <= now:
        return "expired"
    if not token.is_valid(now=now):
        return "expiring"
    return "valid"
