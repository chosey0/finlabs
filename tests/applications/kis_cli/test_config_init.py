from __future__ import annotations

import os
import stat

import pytest
import typer
from typer.testing import CliRunner

from kis_cli.cli.app import CANCEL_EXIT_CODE, _prompt_value_or_exit, app
from kis_cli.config.init import init_config, render_config_template
from kis_cli.config.profiles import (
    ProfileCredentials,
    add_profile,
    config_reference,
    delete_profile,
    env_var_name,
    normalize_expires_at,
    update_profile,
)
from kis_cli.config.resolver import (
    mask_account,
    mask_secret,
    read_config,
    resolve_profile,
    reference_to_env_name,
)

runner = CliRunner()


def test_render_config_template_uses_environment_references() -> None:
    content = render_config_template(profile="real", environment="real")

    assert "active_profile: real" in content
    assert 'app_key: "${KIS_APP_KEY}"' in content
    assert 'app_secret: "${KIS_APP_SECRET}"' in content
    assert "secret-value" not in content


def test_init_config_writes_file_without_secret_values(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"

    result = init_config(profile="real", config_path=config_path)

    assert result.path == config_path
    assert result.profile == "real"
    assert result.environment == "real"
    assert result.overwritten is False
    content = config_path.read_text(encoding="utf-8")
    assert "${KIS_APP_KEY}" in content
    assert "${KIS_APP_SECRET}" in content
    assert "access_token" not in content
    if hasattr(stat, "S_IMODE"):
        assert stat.S_IMODE(config_path.stat().st_mode) == 0o600


def test_init_config_refuses_to_overwrite_without_force(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: true\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        init_config(profile="real", config_path=config_path)

    assert config_path.read_text(encoding="utf-8") == "existing: true\n"


def test_init_config_overwrites_with_force(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: true\n", encoding="utf-8")

    result = init_config(profile="mock", force=True, config_path=config_path)

    assert result.overwritten is True
    content = config_path.read_text(encoding="utf-8")
    assert "active_profile: mock" in content
    assert "environment: mock" in content
    assert "${KIS_MOCK_APP_KEY}" in content


def test_custom_profile_defaults_to_real_environment(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"

    init_config(profile="paper", config_path=config_path)

    content = config_path.read_text(encoding="utf-8")
    assert "active_profile: paper" in content
    assert "environment: real" in content
    assert "${KIS_PAPER_APP_KEY}" in content


def test_typer_config_init_command_writes_config(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"

    result = runner.invoke(
        app,
        [
            "config",
            "init",
            "--profile",
            "real",
            "--path",
            str(config_path),
        ],
    )

    assert result.exit_code == 0
    assert "Config initialized" in result.output
    assert "environment variable references only" in result.output
    assert "${KIS_APP_SECRET}" in config_path.read_text(encoding="utf-8")


def test_typer_config_init_refuses_existing_config(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text("existing: true\n", encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "config",
            "init",
            "--profile",
            "real",
            "--path",
            str(config_path),
        ],
    )

    assert result.exit_code != 0
    assert "config already exists" in result.output
    assert "--force" in result.output


def test_prompt_value_or_exit_exits_on_escape() -> None:
    with pytest.raises(typer.Exit) as exc:
        _prompt_value_or_exit(None)

    assert exc.value.exit_code == CANCEL_EXIT_CODE


def test_prompt_value_or_exit_preserves_blank_input() -> None:
    assert _prompt_value_or_exit("") == ""


def test_add_profile_writes_config_references_and_env_file(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"

    result = add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="12345678",
            app_key="app-key",
            app_secret="secret-key",
            owner="choe",
            expires_at="20261231",
            description="primary account",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )

    assert result.profile_name == "real-main"
    assert result.profile_id == "123e4567-e89b-12d3-a456-426614174000"
    config = config_path.read_text(encoding="utf-8")
    assert "active_profile: real-main" in config
    assert "id: 123e4567-e89b-12d3-a456-426614174000" in config
    assert 'expires_at: "2026-12-31"' in config
    assert 'app_key: "$123e-{KIS_APP}"' in config
    assert 'app_secret: "$123e-{KIS_SECRET}"' in config
    assert 'owner: "$123e-{KIS_OWNER}"' in config
    assert 'account_no: "$123e-{KIS_ACC_NO}"' in config
    assert 'description: "primary account"' in config
    assert "app-key" not in config
    assert "secret-key" not in config

    env = result.env_path.read_text(encoding="utf-8")
    assert 'KIS_123E_APP="app-key"' in env
    assert 'KIS_123E_SECRET="secret-key"' in env
    assert 'KIS_123E_OWNER="choe"' in env
    assert 'KIS_123E_ACC_NO="12345678"' in env
    assert result.env_path.name == "profiles.env"
    assert os.environ["KIS_123E_APP"] == "app-key"


def test_add_profile_preserves_existing_profiles(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"

    add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="111",
            app_key="app-1",
            app_secret="secret-1",
            owner="owner-1",
            expires_at="2026-01-01",
            profile_id="aaaa0000-0000-0000-0000-000000000000",
        ),
        config_path=config_path,
    )
    add_profile(
        ProfileCredentials(
            profile_name="real-sub",
            environment="real",
            account_no="222",
            app_key="app-2",
            app_secret="secret-2",
            owner="owner-2",
            expires_at="2026-02-01",
            profile_id="bbbb0000-0000-0000-0000-000000000000",
        ),
        config_path=config_path,
    )

    config = config_path.read_text(encoding="utf-8")
    assert "active_profile: real-sub" in config
    assert "  real-main:" in config
    assert "  real-sub:" in config
    env = (tmp_path / "profiles.env").read_text(encoding="utf-8")
    assert 'KIS_AAAA_APP="app-1"' in env
    assert 'KIS_BBBB_APP="app-2"' in env


def test_add_profile_refuses_duplicate_without_force(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    credentials = ProfileCredentials(
        profile_name="real-main",
        environment="real",
        account_no="111",
        app_key="app",
        app_secret="secret",
        owner="owner",
        expires_at="2026-01-01",
        profile_id="123e4567-e89b-12d3-a456-426614174000",
    )

    add_profile(credentials, config_path=config_path)

    with pytest.raises(FileExistsError):
        add_profile(credentials, config_path=config_path)


def test_normalize_expires_at_accepts_supported_formats() -> None:
    assert normalize_expires_at("20260507") == "2026-05-07"
    assert normalize_expires_at("2026-05-07") == "2026-05-07"


@pytest.mark.parametrize("expires_at", ["", "2026/05/07", "2026-13-01", "2026-05-07T00:00:00"])
def test_add_profile_rejects_invalid_expires_at(tmp_path, expires_at: str) -> None:
    with pytest.raises(ValueError, match="expires at"):
        add_profile(
            ProfileCredentials(
                profile_name="real-main",
                environment="real",
                account_no="111",
                app_key="app",
                app_secret="secret",
                owner="owner",
                expires_at=expires_at,
                profile_id="123e4567-e89b-12d3-a456-426614174000",
            ),
            config_path=tmp_path / "config.yaml",
        )


def test_config_reference_and_env_var_names_use_uuid_prefix() -> None:
    assert config_reference("123e", "KIS_APP") == "$123e-{KIS_APP}"
    assert env_var_name("123e", "KIS_APP") == "KIS_123E_APP"


def test_resolve_profile_reads_profiles_env(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    monkeypatch.delenv("KIS_123E_APP", raising=False)
    add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="12345678",
            app_key="app-key",
            app_secret="secret-key",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.delenv("KIS_123E_APP", raising=False)
    monkeypatch.delenv("KIS_123E_SECRET", raising=False)
    monkeypatch.delenv("KIS_123E_OWNER", raising=False)
    monkeypatch.delenv("KIS_123E_ACC_NO", raising=False)

    resolved = resolve_profile(config_path=config_path)

    assert resolved.name == "real-main"
    assert resolved.environment == "real"
    assert resolved.app_key == "app-key"
    assert resolved.app_secret == "secret-key"
    assert resolved.owner == "choe"
    assert resolved.account_no == "12345678"
    assert resolved.expires_at == "2026-12-31"


def test_resolve_profile_allows_environment_override(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="12345678",
            app_key="app-key",
            app_secret="secret-key",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.setenv("KIS_123E_APP", "override-key")

    resolved = resolve_profile(config_path=config_path)

    assert resolved.app_key == "override-key"


def test_resolve_profile_reports_missing_env_value(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """active_profile: real-main

profiles:
  real-main:
    id: 123e4567-e89b-12d3-a456-426614174000
    environment: real
    expires_at: "2026-12-31"
    app_key: "$123e-{KIS_APP}"
    app_secret: "$123e-{KIS_SECRET}"
    owner: "$123e-{KIS_OWNER}"
    account_no: "$123e-{KIS_ACC_NO}"
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("KIS_123E_APP", raising=False)

    with pytest.raises(ValueError, match="KIS_123E_APP"):
        resolve_profile(config_path=config_path)


def test_typer_config_validate_masks_secret_values(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="12345678",
            app_key="app-key-value",
            app_secret="secret-value",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )

    result = runner.invoke(
        app,
        ["config", "validate", "--path", str(config_path)],
    )

    assert result.exit_code == 0
    assert "Config validation" in result.output
    assert "valid" in result.output
    assert "app-key-value" not in result.output
    assert "secret-value" not in result.output
    assert "1234****" in result.output


def test_read_config_and_reference_helpers(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """active_profile: real-main

profiles:
  real-main:
    id: 123e4567-e89b-12d3-a456-426614174000
    environment: real
    expires_at: "2026-12-31"
    app_key: "$123e-{KIS_APP}"
    app_secret: "$123e-{KIS_SECRET}"
    owner: "$123e-{KIS_OWNER}"
    account_no: "$123e-{KIS_ACC_NO}"
""",
        encoding="utf-8",
    )

    active_profile, profiles = read_config(config_path)

    assert active_profile == "real-main"
    assert profiles["real-main"].values["environment"] == "real"
    assert profiles["real-main"].values["expires_at"] == "2026-12-31"
    assert reference_to_env_name("$123e-{KIS_APP}") == "KIS_123E_APP"
    assert reference_to_env_name("${KIS_APP_KEY}") == "KIS_APP_KEY"
    assert mask_account("12345678") == "1234****"
    assert mask_secret("abcdef") == "abcd********"


def test_update_profile_preserves_id_and_rewrites_env_values(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="11111111",
            app_key="old-app",
            app_secret="old-secret",
            owner="old-owner",
            expires_at="2026-01-01",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )

    result = update_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="mock",
            account_no="22222222",
            app_key="new-app",
            app_secret="new-secret",
            owner="new-owner",
            expires_at="20261231",
            description="updated",
        ),
        config_path=config_path,
    )

    assert result.profile_id == "123e4567-e89b-12d3-a456-426614174000"
    config = config_path.read_text(encoding="utf-8")
    assert "environment: mock" in config
    assert 'expires_at: "2026-12-31"' in config
    assert 'description: "updated"' in config
    assert "new-app" not in config
    env = (tmp_path / "profiles.env").read_text(encoding="utf-8")
    assert 'KIS_123E_APP="new-app"' in env
    assert 'KIS_123E_SECRET="new-secret"' in env
    assert 'KIS_123E_OWNER="new-owner"' in env
    assert 'KIS_123E_ACC_NO="22222222"' in env


def test_delete_profile_removes_profile_and_env_values(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="real-main",
            environment="real",
            account_no="111",
            app_key="app-1",
            app_secret="secret-1",
            owner="owner-1",
            expires_at="2026-01-01",
            profile_id="aaaa0000-0000-0000-0000-000000000000",
        ),
        config_path=config_path,
    )
    add_profile(
        ProfileCredentials(
            profile_name="real-sub",
            environment="real",
            account_no="222",
            app_key="app-2",
            app_secret="secret-2",
            owner="owner-2",
            expires_at="2026-02-01",
            profile_id="bbbb0000-0000-0000-0000-000000000000",
        ),
        config_path=config_path,
    )

    result = delete_profile("real-sub", config_path=config_path)

    assert result.profile_name == "real-sub"
    assert result.active_profile == "real-main"
    config = config_path.read_text(encoding="utf-8")
    assert "  real-main:" in config
    assert "  real-sub:" not in config
    assert "active_profile: real-main" in config
    env = (tmp_path / "profiles.env").read_text(encoding="utf-8")
    assert "KIS_AAAA_APP" in env
    assert "KIS_BBBB_APP" not in env


def test_typer_config_help_shows_update_and_delete() -> None:
    result = runner.invoke(app, ["config", "--help"])

    assert result.exit_code == 0
    assert "update" in result.output
    assert "delete" in result.output
