from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.app.broker_registry import build_client
from finlabs_cli.app.token_store import JsonTokenStore, StoredToken
from finlabs_cli.main import app
from finlabs_cli.models.account import Account
from finlabs_cli.ui import prompts


def test_app_exposes_command_groups() -> None:
    result = CliRunner().invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "accounts" in result.output
    assert "auth" in result.output
    assert "chart" in result.output
    assert "realtime" in result.output


def test_account_store_round_trips_accounts(tmp_path: Path) -> None:
    store = AccountStore(tmp_path / "accounts.json")
    account = Account(
        id="account-1",
        alias="kiwoom-main",
        broker="kiwoom",
        owner_name="owner",
        environment="mock",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "secret_key": "secret"},
    )

    store.add(account)

    assert store.require("kiwoom-main") == account
    assert store.list() == [account]


def test_token_store_round_trips_namespaced_records(tmp_path: Path) -> None:
    store = JsonTokenStore(tmp_path / "tokens.json", namespace="kiwoom-main")
    expires_at = datetime.now(UTC) + timedelta(hours=1)

    store.set(
        "mock:app",
        StoredToken(
            access_token="token",
            token_type="bearer",
            expires_at=expires_at,
        ),
    )

    record = store.get("mock:app")
    assert record is not None
    assert record.access_token == "token"
    assert not record.is_expired(now=datetime.now(UTC))
    assert list(store.records()) == ["mock:app"]


def test_broker_registry_builds_kiwoom_client(tmp_path: Path) -> None:
    account = Account(
        id="account-1",
        alias="kiwoom-main",
        broker="kiwoom",
        owner_name="owner",
        environment="mock",
        expires_at="2027-01-01",
        credentials={"app_key": "app", "secret_key": "secret"},
    )

    client = build_client(account, JsonTokenStore(tmp_path / "tokens.json"))

    assert client.credentials.app_key == "app"
    assert client.environment == "mock"


def test_text_prompt_applies_default_without_passing_prompt_default(monkeypatch) -> None:
    captured = {}

    class FakeTextPrompt:
        def __init__(self, message: str) -> None:
            captured["message"] = message

        def ask(self) -> str:
            return ""

    monkeypatch.setattr(prompts, "TextPrompt", FakeTextPrompt)

    assert prompts.text("Expired At", default="2026-06-17") == "2026-06-17"
    assert captured["message"] == "Expired At (2026-06-17)"
