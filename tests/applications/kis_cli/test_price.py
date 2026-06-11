from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from modules.brokers.kis import (
    CurrentPrice,
    KisAuthError,
    parse_overseas_current_price,
)
from kis_cli.config.resolver import ResolvedProfile
from kis_cli.services.auth import call_with_sdk_client


def test_parse_overseas_current_price_normalizes_common_fields() -> None:
    price = parse_overseas_current_price(
        market="NASDAQ",
        symbol="AAPL",
        output={
            "name": "Apple Inc.",
            "last": "190.25",
            "curr": "USD",
            "diff": "1.23",
            "rate": "0.65",
            "open": "189.00",
            "high": "191.00",
            "low": "188.50",
            "tvol": "987654",
        },
    )

    assert price.market == "NASDAQ"
    assert price.symbol == "AAPL"
    assert price.name == "Apple Inc."
    assert price.price == Decimal("190.25")
    assert price.currency == "USD"
    assert price.change == Decimal("1.23")
    assert price.change_rate == Decimal("0.65")
    assert price.volume == 987654


def test_call_with_sdk_client_refreshes_token_once_after_auth_error(monkeypatch) -> None:
    attempts = {"count": 0}

    async def fake_run_with_sdk_client(operation, resolved):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise KisAuthError("token expired")
        return await operation(object())

    async def fake_operation(client) -> CurrentPrice:
        return CurrentPrice(
            market="NASDAQ",
            symbol="AAPL",
            name="Apple Inc.",
            price=Decimal("190.25"),
            currency="USD",
            change=None,
            change_rate=None,
            open=None,
            high=None,
            low=None,
            volume=None,
        )

    monkeypatch.setattr("kis_cli.services.auth.resolve_profile", _fake_resolve_profile)
    monkeypatch.setattr("kis_cli.services.auth._run_with_sdk_client", fake_run_with_sdk_client)


    result = call_with_sdk_client(fake_operation, profile="csq1404")
    assert result.symbol == "AAPL"
    assert attempts["count"] == 2


def test_call_with_sdk_client_does_not_retry_more_than_once(monkeypatch) -> None:
    attempts = {"count": 0}

    async def always_fail_run(operation, resolved):
        attempts["count"] += 1
        raise KisAuthError("token expired")

    async def fake_operation(client) -> CurrentPrice:
        raise AssertionError("operation should not run")

    monkeypatch.setattr("kis_cli.services.auth.resolve_profile", _fake_resolve_profile)
    monkeypatch.setattr("kis_cli.services.auth._run_with_sdk_client", always_fail_run)

    try:
        call_with_sdk_client(fake_operation, profile="csq1404")
    except KisAuthError:
        pass
    else:
        raise AssertionError("expected KisAuthError")

    assert attempts["count"] == 2


def test_call_with_sdk_client_does_not_retry_token_issue_rate_limit(monkeypatch) -> None:
    attempts = {"count": 0}

    async def fail_token_issue(operation, resolved):
        attempts["count"] += 1
        raise KisAuthError("KIS token request failed: 접근토큰 발급 잠시 후 다시 시도하세요(1분당 1회)")

    async def fake_operation(client) -> CurrentPrice:
        raise AssertionError("operation should not run")

    monkeypatch.setattr("kis_cli.services.auth.resolve_profile", _fake_resolve_profile)
    monkeypatch.setattr("kis_cli.services.auth._run_with_sdk_client", fail_token_issue)

    try:
        call_with_sdk_client(fake_operation, profile="csq1404")
    except KisAuthError as exc:
        assert "1분당 1회" in str(exc)
    else:
        raise AssertionError("expected KisAuthError")

    assert attempts["count"] == 1


def _fake_resolve_profile(*, profile=None, config_path=None) -> ResolvedProfile:
    return ResolvedProfile(
        name=profile or "csq1404",
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
