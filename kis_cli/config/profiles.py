from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from kis_cli.config.init import _chmod_owner_read_write, _normalize_profile
from kis_cli.config.paths import default_config_file

SUPPORTED_ENVIRONMENTS = {"real", "mock"}
ENV_FILE_NAME = "profiles.env"


@dataclass(frozen=True)
class ProfileCredentials:
    profile_name: str
    environment: str
    account_no: str
    app_key: str
    app_secret: str
    owner: str
    expires_at: str
    description: str = ""
    profile_id: str | None = None


@dataclass(frozen=True)
class ProfileAddResult:
    config_path: Path
    env_path: Path
    profile_name: str
    profile_id: str
    environment: str
    updated_existing_config: bool


@dataclass(frozen=True)
class ProfileDeleteResult:
    config_path: Path
    env_path: Path
    profile_name: str
    profile_id: str
    active_profile: str


def add_profile(
    credentials: ProfileCredentials,
    *,
    config_path: Path | None = None,
    force: bool = False,
) -> ProfileAddResult:
    profile_name = _normalize_profile(credentials.profile_name)
    environment = _normalize_environment(credentials.environment)
    _require_value("account number", credentials.account_no)
    _require_value("app key", credentials.app_key)
    _require_value("secret key", credentials.app_secret)
    _require_value("owner", credentials.owner)
    expires_at = normalize_expires_at(credentials.expires_at)

    profile_id = credentials.profile_id or str(uuid4())
    prefix = profile_id[:4].lower()
    path = (config_path or default_config_file()).expanduser()
    existed_before = path.exists()

    profiles = _read_known_profiles(path) if existed_before else {}
    if profile_name in profiles and not force:
        raise FileExistsError(
            f"profile '{profile_name}' already exists in {path}; pass --force to overwrite"
        )

    profiles[profile_name] = _render_profile_block(
        profile_name=profile_name,
        profile_id=profile_id,
        prefix=prefix,
        environment=environment,
        expires_at=expires_at,
        description=credentials.description.strip(),
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render_config(profile_name, profiles), encoding="utf-8")
    _chmod_owner_read_write(path)

    env_path = path.parent / ENV_FILE_NAME
    _upsert_env_values(
        env_path,
        prefix=prefix,
        app_key=credentials.app_key,
        app_secret=credentials.app_secret,
        owner=credentials.owner,
        account_no=credentials.account_no,
    )

    return ProfileAddResult(
        config_path=path,
        env_path=env_path,
        profile_name=profile_name,
        profile_id=profile_id,
        environment=environment,
        updated_existing_config=existed_before,
    )


def update_profile(
    credentials: ProfileCredentials,
    *,
    config_path: Path | None = None,
) -> ProfileAddResult:
    profile_name = _normalize_profile(credentials.profile_name)
    path = (config_path or default_config_file()).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"config not found at {path}")

    profiles = _read_known_profiles(path)
    if profile_name not in profiles:
        raise ValueError(f"profile '{profile_name}' not found in {path}")

    existing_values = _profile_values_from_lines(profiles[profile_name])
    profile_id = credentials.profile_id or existing_values.get("id") or str(uuid4())
    updated_credentials = ProfileCredentials(
        profile_name=profile_name,
        environment=credentials.environment,
        account_no=credentials.account_no,
        app_key=credentials.app_key,
        app_secret=credentials.app_secret,
        owner=credentials.owner,
        expires_at=credentials.expires_at,
        description=credentials.description,
        profile_id=profile_id,
    )
    result = add_profile(updated_credentials, config_path=path, force=True)
    return ProfileAddResult(
        config_path=result.config_path,
        env_path=result.env_path,
        profile_name=result.profile_name,
        profile_id=result.profile_id,
        environment=result.environment,
        updated_existing_config=True,
    )


def delete_profile(
    profile_name: str,
    *,
    config_path: Path | None = None,
) -> ProfileDeleteResult:
    normalized_profile = _normalize_profile(profile_name)
    path = (config_path or default_config_file()).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"config not found at {path}")

    profiles = _read_known_profiles(path)
    if normalized_profile not in profiles:
        raise ValueError(f"profile '{normalized_profile}' not found in {path}")

    values = _profile_values_from_lines(profiles[normalized_profile])
    profile_id = values.get("id", "")
    prefix = profile_id[:4].lower()
    del profiles[normalized_profile]

    active_profile = _read_active_profile(path)
    if active_profile == normalized_profile:
        active_profile = next(iter(profiles), "")

    path.write_text(_render_config(active_profile, profiles), encoding="utf-8")
    _chmod_owner_read_write(path)

    env_path = path.parent / ENV_FILE_NAME
    if prefix:
        _remove_env_values(env_path, prefix=prefix)

    return ProfileDeleteResult(
        config_path=path,
        env_path=env_path,
        profile_name=normalized_profile,
        profile_id=profile_id,
        active_profile=active_profile,
    )


def config_reference(prefix: str, key: str) -> str:
    return f"${prefix}-{{{key}}}"


def env_var_name(prefix: str, key: str) -> str:
    suffix = key.removeprefix("KIS_")
    return f"KIS_{prefix.upper()}_{suffix}"


def _normalize_environment(environment: str) -> str:
    normalized = environment.strip().lower()
    if normalized not in SUPPORTED_ENVIRONMENTS:
        allowed = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ValueError(f"environment must be one of: {allowed}")
    return normalized


def normalize_expires_at(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("expires at must not be empty")

    try:
        if len(normalized) == 8 and normalized.isdigit():
            return datetime.strptime(normalized, "%Y%m%d").date().isoformat()
        if len(normalized) == 10:
            return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise ValueError("expires at must be YYYYMMDD or YYYY-MM-DD") from exc

    raise ValueError("expires at must be YYYYMMDD or YYYY-MM-DD")


def _require_value(label: str, value: str) -> None:
    if not value.strip():
        raise ValueError(f"{label} must not be empty")


def _render_profile_block(
    *,
    profile_name: str,
    profile_id: str,
    prefix: str,
    environment: str,
    expires_at: str,
    description: str,
) -> list[str]:
    lines = [
        f"  {profile_name}:",
        f"    id: {profile_id}",
        f"    environment: {environment}",
        f"    expires_at: \"{_escape_yaml_string(expires_at)}\"",
        f"    app_key: \"{config_reference(prefix, 'KIS_APP')}\"",
        f"    app_secret: \"{config_reference(prefix, 'KIS_SECRET')}\"",
        f"    owner: \"{config_reference(prefix, 'KIS_OWNER')}\"",
        f"    account_no: \"{config_reference(prefix, 'KIS_ACC_NO')}\"",
    ]
    if description:
        lines.append(f"    description: \"{_escape_yaml_string(description)}\"")
    return lines


def _render_config(active_profile: str, profiles: dict[str, list[str]]) -> str:
    lines = [f"active_profile: {active_profile}", "", "profiles:"]
    for profile_lines in profiles.values():
        lines.extend(profile_lines)
    return "\n".join(lines) + "\n"


def _read_known_profiles(path: Path) -> dict[str, list[str]]:
    profiles: dict[str, list[str]] = {}
    current_name: str | None = None
    current_lines: list[str] = []
    in_profiles = False

    for line in path.read_text(encoding="utf-8").splitlines():
        if line == "profiles:":
            in_profiles = True
            continue
        if not in_profiles:
            continue
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            if current_name is not None:
                profiles[current_name] = current_lines
            current_name = line.strip()[:-1]
            current_lines = [line]
            continue
        if current_name is not None and line.strip():
            current_lines.append(line)

    if current_name is not None:
        profiles[current_name] = current_lines

    return profiles


def _read_active_profile(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("active_profile:"):
            return _clean_scalar(line.split(":", 1)[1])
    return ""


def _profile_values_from_lines(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines[1:]:
        if not line.startswith("    ") or ":" not in line:
            continue
        key, value = line.strip().split(":", 1)
        values[key] = _clean_scalar(value)
    return values


def _upsert_env_values(
    path: Path,
    *,
    prefix: str,
    app_key: str,
    app_secret: str,
    owner: str,
    account_no: str,
) -> None:
    values = {
        env_var_name(prefix, "KIS_APP"): app_key,
        env_var_name(prefix, "KIS_SECRET"): app_secret,
        env_var_name(prefix, "KIS_OWNER"): owner,
        env_var_name(prefix, "KIS_ACC_NO"): account_no,
    }
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            existing[key] = value

    existing.update({key: _quote_env_value(value) for key, value in values.items()})
    os.environ.update(values)
    content = "\n".join(f"{key}={value}" for key, value in sorted(existing.items())) + "\n"
    path.write_text(content, encoding="utf-8")
    _chmod_owner_read_write(path)


def upsert_env_value(path: Path, key: str, value: str) -> None:
    existing: dict[str, str] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            existing_key, existing_value = line.split("=", 1)
            existing[existing_key] = existing_value

    existing[key] = _quote_env_value(value)
    os.environ[key] = value
    content = "\n".join(f"{name}={stored}" for name, stored in sorted(existing.items())) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _chmod_owner_read_write(path)


def _remove_env_values(path: Path, *, prefix: str) -> None:
    if not path.exists():
        return
    remove_names = {
        env_var_name(prefix, "KIS_APP"),
        env_var_name(prefix, "KIS_SECRET"),
        env_var_name(prefix, "KIS_OWNER"),
        env_var_name(prefix, "KIS_ACC_NO"),
    }
    remaining: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key not in remove_names:
            remaining[key] = value
        else:
            os.environ.pop(key, None)

    content = "\n".join(f"{key}={value}" for key, value in sorted(remaining.items()))
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")
    _chmod_owner_read_write(path)


def _quote_env_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _escape_yaml_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _clean_scalar(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in ("'", '"'):
        return stripped[1:-1]
    return stripped
