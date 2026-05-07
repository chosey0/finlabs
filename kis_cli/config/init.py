from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from kis_cli.config.paths import default_config_file

SUPPORTED_ENVIRONMENTS = {"real", "mock"}


@dataclass(frozen=True)
class ConfigInitResult:
    path: Path
    profile: str
    environment: str
    overwritten: bool


def init_config(
    *,
    profile: str,
    environment: str | None = None,
    force: bool = False,
    config_path: Path | None = None,
) -> ConfigInitResult:
    normalized_profile = _normalize_profile(profile)
    normalized_environment = _resolve_environment(normalized_profile, environment)
    path = config_path or default_config_file()
    path = path.expanduser()
    existed_before = path.exists()

    if existed_before and not force:
        raise FileExistsError(f"config already exists at {path}; pass --force to overwrite")

    path.parent.mkdir(parents=True, exist_ok=True)
    content = render_config_template(
        profile=normalized_profile,
        environment=normalized_environment,
    )
    path.write_text(content, encoding="utf-8")
    _chmod_owner_read_write(path)

    return ConfigInitResult(
        path=path,
        profile=normalized_profile,
        environment=normalized_environment,
        overwritten=existed_before and force,
    )


def render_config_template(*, profile: str, environment: str) -> str:
    upper_profile = profile.upper().replace("-", "_")
    prefix = "KIS" if profile == "real" else f"KIS_{upper_profile}"
    return f"""active_profile: {profile}

profiles:
  {profile}:
    environment: {environment}
    app_key: "${{{prefix}_APP_KEY}}"
    app_secret: "${{{prefix}_APP_SECRET}}"
    account_no: "${{{prefix}_ACCOUNT_NO}}"
    account_product_code: "${{{prefix}_ACCOUNT_PRODUCT_CODE}}"
"""


def _normalize_profile(profile: str) -> str:
    normalized = profile.strip().lower()
    if not normalized:
        raise ValueError("profile must not be empty")
    if not all(ch.isalnum() or ch in ("-", "_") for ch in normalized):
        raise ValueError("profile may contain only letters, digits, hyphens, and underscores")
    return normalized


def _resolve_environment(profile: str, environment: str | None) -> str:
    if environment is None:
        environment = profile if profile in SUPPORTED_ENVIRONMENTS else "real"
    if environment not in SUPPORTED_ENVIRONMENTS:
        allowed = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ValueError(f"environment must be one of: {allowed}")
    return environment


def _chmod_owner_read_write(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError:
        # Some platforms or filesystems do not support POSIX mode changes.
        pass
