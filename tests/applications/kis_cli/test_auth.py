from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from modules.brokers.kis import IssuedToken, KisAuthError, TokenRecord, mask_sensitive_message, parse_token_response

from kis_cli.cli.app import app
from kis_cli.config.profiles import ProfileCredentials, add_profile
from kis_cli.config.resolver import ResolvedProfile
from kis_cli.core.token_cache import read_cached_token, read_cached_token_result, write_cached_token
from kis_cli.services.auth import _CliSdkTokenCache

runner = CliRunner()


def test_parse_token_response_uses_expires_in() -> None:
    issued_at = datetime(2026, 5, 7, 1, 0, tzinfo=UTC)

    token = parse_token_response(
        {
            "access_token": "secret-token",
            "token_type": "Bearer",
            "expires_in": "86400",
        },
        issued_at=issued_at,
    )

    assert token.access_token == "secret-token"
    assert token.token_type == "Bearer"
    assert token.expires_at == issued_at + timedelta(seconds=86400)


def test_parse_token_response_rejects_missing_access_token() -> None:
    issued_at = datetime(2026, 5, 7, 1, 0, tzinfo=UTC)

    try:
        parse_token_response({"msg1": "invalid credentials"}, issued_at=issued_at)
    except KisAuthError as exc:
        assert "access_token" in str(exc)
        assert "invalid credentials" in str(exc)
    else:
        raise AssertionError("expected KisAuthError")


def test_mask_sensitive_message_masks_token_like_values() -> None:
    message = "bad appkey='abc123456789' appsecret: sec987654321 access_token=tok123456789"

    masked = mask_sensitive_message(message)

    assert "abc123456789" not in masked
    assert "sec987654321" not in masked
    assert "tok123456789" not in masked
    assert "appkey='********" in masked


def test_token_cache_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path)
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=1)

    cached = write_cached_token(
        IssuedToken(
            access_token="secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=expires_at,
            raw={},
        ),
        profile_id="profile-id",
        profile_name="csq1404",
        environment="real",
    )
    loaded = read_cached_token(profile_id="profile-id")

    assert cached.path == tmp_path / "tokens" / "profile-id.json"
    assert loaded is not None
    assert loaded.access_token == "secret-token"
    assert loaded.is_valid(now=issued_at)
    assert "secret-token" in cached.path.read_text(encoding="utf-8")


def test_cli_sdk_token_cache_reuses_persistent_cli_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path)
    issued_at = datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=1)
    resolved = _resolved_profile()

    write_cached_token(
        IssuedToken(
            access_token="persistent-secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=expires_at,
            raw={},
        ),
        profile_id=resolved.profile_id,
        profile_name=resolved.name,
        environment=resolved.environment,
    )

    record = _CliSdkTokenCache(resolved).get("real:app-key")

    assert record == TokenRecord(
        access_token="persistent-secret-token",
        token_type="Bearer",
        expires_at=expires_at,
    )


def test_token_cache_reports_invalid_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path)
    path = tmp_path / "tokens" / "profile-id.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    result = read_cached_token_result(profile_id="profile-id")

    assert result.status == "invalid"
    assert result.token is None


def _resolved_profile() -> ResolvedProfile:
    return ResolvedProfile(
        name="csq1404",
        profile_id="profile-id",
        environment="real",
        expires_at="2026-12-31",
        app_key="app-key",
        app_secret="app-secret",
        owner="choe",
        account_no="12345678",
        description="",
        config_path=Path("config.yaml"),
        env_path=Path("profiles.env"),
    )


def test_auth_test_command_issues_token_without_printing_secret(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="csq1404",
            environment="real",
            account_no="12345678",
            app_key="app-key-secret",
            app_secret="app-secret-secret",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path / "cache")

    def fake_issue_access_token(*, environment: str, app_key: str, app_secret: str) -> IssuedToken:
        assert environment == "real"
        assert app_key == "app-key-secret"
        assert app_secret == "app-secret-secret"
        issued_at = datetime(2026, 5, 7, 1, 0, tzinfo=UTC)
        return IssuedToken(
            access_token="issued-secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=24),
            raw={},
        )

    monkeypatch.setattr("kis_cli.services.auth.issue_access_token", fake_issue_access_token)

    result = runner.invoke(
        app,
        ["auth", "test", "--profile", "csq1404", "--path", str(config_path)],
    )

    assert result.exit_code == 0
    assert "Auth test" in result.output
    assert "issued" in result.output
    assert "2026-05-08 10:00:00 KST" in result.output
    assert "issued-secret-token" not in result.output
    assert "app-key-secret" not in result.output
    assert "app-secret-secret" not in result.output


def test_auth_test_command_reuses_valid_cached_token(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="csq1404",
            environment="real",
            account_no="12345678",
            app_key="app-key-secret",
            app_secret="app-secret-secret",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path / "cache")
    issued_at = datetime.now(UTC)
    write_cached_token(
        IssuedToken(
            access_token="cached-secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
            raw={},
        ),
        profile_id="123e4567-e89b-12d3-a456-426614174000",
        profile_name="csq1404",
        environment="real",
    )

    def fail_issue_access_token(*, environment: str, app_key: str, app_secret: str) -> IssuedToken:
        raise AssertionError("cached token should be reused")

    monkeypatch.setattr("kis_cli.services.auth.issue_access_token", fail_issue_access_token)

    result = runner.invoke(
        app,
        ["auth", "test", "--profile", "csq1404", "--path", str(config_path)],
    )

    assert result.exit_code == 0
    assert "reused" in result.output
    assert "cached-secret-token" not in result.output


def test_auth_status_reports_none_for_profile_without_token(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="csq1404",
            environment="real",
            account_no="12345678",
            app_key="app-key-secret",
            app_secret="app-secret-secret",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path / "cache")

    result = runner.invoke(
        app,
        ["auth", "status", "--profile", "csq1404", "--path", str(config_path)],
    )

    assert result.exit_code == 0
    assert "Auth status" in result.output
    assert "csq1404" in result.output
    assert "none" in result.output
    assert "app-key-secret" not in result.output
    assert "app-secret-secret" not in result.output


def test_auth_status_reports_valid_and_expired_tokens_for_all_profiles(
    tmp_path,
    monkeypatch,
) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="valid",
            environment="real",
            account_no="11111111",
            app_key="app-key-1",
            app_secret="app-secret-1",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="aaaa4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    add_profile(
        ProfileCredentials(
            profile_name="expiring",
            environment="real",
            account_no="22222222",
            app_key="app-key-2",
            app_secret="app-secret-2",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="bbbb4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    add_profile(
        ProfileCredentials(
            profile_name="old",
            environment="real",
            account_no="33333333",
            app_key="app-key-3",
            app_secret="app-secret-3",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="cccc4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path / "cache")
    issued_at = datetime.now(UTC)
    write_cached_token(
        IssuedToken(
            access_token="valid-secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
            raw={},
        ),
        profile_id="aaaa4567-e89b-12d3-a456-426614174000",
        profile_name="valid",
        environment="real",
    )
    write_cached_token(
        IssuedToken(
            access_token="expired-secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(minutes=2),
            raw={},
        ),
        profile_id="bbbb4567-e89b-12d3-a456-426614174000",
        profile_name="expiring",
        environment="real",
    )
    write_cached_token(
        IssuedToken(
            access_token="old-secret-token",
            token_type="Bearer",
            issued_at=issued_at - timedelta(hours=2),
            expires_at=issued_at - timedelta(hours=1),
            raw={},
        ),
        profile_id="cccc4567-e89b-12d3-a456-426614174000",
        profile_name="old",
        environment="real",
    )

    result = runner.invoke(
        app,
        ["auth", "status", "--all", "--path", str(config_path)],
    )

    assert result.exit_code == 0
    assert "valid" in result.output
    assert "expiring" in result.output
    assert "old" in result.output
    assert "expired" in result.output
    assert "Expires in" in result.output
    assert "KST" in result.output
    assert "valid-secret-token" not in result.output
    assert "expired-secret-token" not in result.output
    assert "old-secret-token" not in result.output


def test_auth_status_rejects_profile_and_all_together(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="csq1404",
            environment="real",
            account_no="12345678",
            app_key="app-key-secret",
            app_secret="app-secret-secret",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )

    result = runner.invoke(
        app,
        ["auth", "status", "--profile", "csq1404", "--all", "--path", str(config_path)],
    )

    assert result.exit_code != 0
    assert "pass either --profile or --all" in result.output


def test_auth_clear_removes_cached_token(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="csq1404",
            environment="real",
            account_no="12345678",
            app_key="app-key-secret",
            app_secret="app-secret-secret",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path / "cache")
    issued_at = datetime.now(UTC)
    cached = write_cached_token(
        IssuedToken(
            access_token="cached-secret-token",
            token_type="Bearer",
            issued_at=issued_at,
            expires_at=issued_at + timedelta(hours=1),
            raw={},
        ),
        profile_id="123e4567-e89b-12d3-a456-426614174000",
        profile_name="csq1404",
        environment="real",
    )

    result = runner.invoke(
        app,
        ["auth", "clear", "--profile", "csq1404", "--path", str(config_path)],
    )

    assert result.exit_code == 0
    assert "Auth cache cleared" in result.output
    assert "yes" in result.output
    assert not cached.path.exists()
    assert "cached-secret-token" not in result.output


def test_auth_clear_rejects_profile_and_all_together(tmp_path) -> None:
    config_path = tmp_path / "config.yaml"
    add_profile(
        ProfileCredentials(
            profile_name="csq1404",
            environment="real",
            account_no="12345678",
            app_key="app-key-secret",
            app_secret="app-secret-secret",
            owner="choe",
            expires_at="2026-12-31",
            profile_id="123e4567-e89b-12d3-a456-426614174000",
        ),
        config_path=config_path,
    )

    result = runner.invoke(
        app,
        ["auth", "clear", "--profile", "csq1404", "--all", "--path", str(config_path)],
    )

    assert result.exit_code != 0
    assert "pass either --profile or --all" in result.output
