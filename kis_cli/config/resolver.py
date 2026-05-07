from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from kis_cli.config.paths import default_config_file
from kis_cli.config.profiles import (
    ENV_FILE_NAME,
    SUPPORTED_ENVIRONMENTS,
    env_var_name,
    normalize_expires_at,
)

UUID_REFERENCE_RE = re.compile(r"^\$([A-Za-z0-9]{4})-\{([A-Za-z0-9_]+)\}$")
ENV_REFERENCE_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
REQUIRED_FIELDS = (
    "id",
    "environment",
    "expires_at",
    "app_key",
    "app_secret",
    "owner",
    "account_no",
)


@dataclass(frozen=True)
class RawProfile:
    name: str
    values: dict[str, str]


@dataclass(frozen=True)
class ResolvedProfile:
    name: str
    profile_id: str
    environment: str
    expires_at: str
    app_key: str
    app_secret: str
    owner: str
    account_no: str
    description: str
    config_path: Path
    env_path: Path


def resolve_profile(
    *,
    profile: str | None = None,
    config_path: Path | None = None,
) -> ResolvedProfile:
    path = (config_path or default_config_file()).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"config not found at {path}")

    active_profile, profiles = read_config(path)
    profile_name = profile or active_profile
    if not profile_name:
        raise ValueError("active_profile is missing; pass --profile explicitly")
    if profile_name not in profiles:
        raise ValueError(f"profile '{profile_name}' not found in {path}")

    raw = profiles[profile_name]
    _validate_required_fields(raw)
    environment = raw.values["environment"]
    if environment not in SUPPORTED_ENVIRONMENTS:
        allowed = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ValueError(f"profile '{profile_name}' environment must be one of: {allowed}")

    env_path = path.parent / ENV_FILE_NAME
    env_values = read_env_file(env_path)
    env_values.update(os.environ)

    return ResolvedProfile(
        name=profile_name,
        profile_id=raw.values["id"],
        environment=environment,
        expires_at=normalize_expires_at(raw.values["expires_at"]),
        app_key=resolve_reference(raw.values["app_key"], env_values),
        app_secret=resolve_reference(raw.values["app_secret"], env_values),
        owner=resolve_reference(raw.values["owner"], env_values),
        account_no=resolve_reference(raw.values["account_no"], env_values),
        description=raw.values.get("description", ""),
        config_path=path,
        env_path=env_path,
    )


def read_config(path: Path) -> tuple[str | None, dict[str, RawProfile]]:
    active_profile: str | None = None
    profiles: dict[str, RawProfile] = {}
    current_name: str | None = None
    current_values: dict[str, str] = {}
    in_profiles = False

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line.startswith("active_profile:"):
            active_profile = _clean_scalar(line.split(":", 1)[1])
            continue
        if line == "profiles:":
            in_profiles = True
            continue
        if not in_profiles:
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            if current_name is not None:
                profiles[current_name] = RawProfile(current_name, current_values)
            current_name = line.strip()[:-1]
            current_values = {}
            continue
        if current_name is not None and line.startswith("    ") and ":" in line:
            key, value = line.strip().split(":", 1)
            current_values[key] = _clean_scalar(value)

    if current_name is not None:
        profiles[current_name] = RawProfile(current_name, current_values)

    return active_profile, profiles


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = _unquote_env_value(value)
    return values


def resolve_reference(value: str, env_values: dict[str, str]) -> str:
    variable = reference_to_env_name(value)
    if variable is None:
        if value:
            return value
        raise ValueError("empty config value cannot be resolved")
    if variable not in env_values or not env_values[variable]:
        raise ValueError(f"missing environment value: {variable}")
    return env_values[variable]


def reference_to_env_name(value: str) -> str | None:
    uuid_match = UUID_REFERENCE_RE.match(value)
    if uuid_match:
        prefix, key = uuid_match.groups()
        return env_var_name(prefix, key)

    env_match = ENV_REFERENCE_RE.match(value)
    if env_match:
        return env_match.group(1)

    return None


def mask_secret(value: str, *, visible: int = 4) -> str:
    if not value:
        return ""
    if len(value) <= visible:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * 8}"


def mask_account(value: str) -> str:
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:4]}{'*' * 4}"


def _validate_required_fields(profile: RawProfile) -> None:
    missing = [field for field in REQUIRED_FIELDS if not profile.values.get(field)]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"profile '{profile.name}' is missing required field(s): {joined}")


def _clean_scalar(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        return stripped[1:-1]
    return stripped


def _unquote_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        stripped = stripped[1:-1]
    return stripped.replace('\\"', '"').replace("\\\\", "\\")
