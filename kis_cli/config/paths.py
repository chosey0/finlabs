from __future__ import annotations

from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir, user_data_dir, user_log_dir

APP_NAME = "kis-cli"


def config_dir() -> Path:
    return Path(user_config_dir(APP_NAME))


def cache_dir() -> Path:
    return Path(user_cache_dir(APP_NAME))


def data_dir() -> Path:
    return Path(user_data_dir(APP_NAME))


def log_dir() -> Path:
    return Path(user_log_dir(APP_NAME))


def default_config_file() -> Path:
    return config_dir() / "config.yaml"
