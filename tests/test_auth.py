from __future__ import annotations

from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from kis_cli.cli.app import app
from kis_cli.config.profiles import ProfileCredentials, add_profile
from kis_cli.core.auth import IssuedToken, KisAuthError, parse_token_response
from kis_cli.core.token_cache import read_cached_token, write_cached_token

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


def test_token_cache_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("kis_cli.core.token_cache.cache_dir", lambda: tmp_path)
    issued_at = datetime(2026, 5, 7, 1, 0, tzinfo=UTC)
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
