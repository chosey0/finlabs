from __future__ import annotations

from datetime import date

import typer

from finlabs_cli.app.account_store import AccountStore
from finlabs_cli.models.account import Account, new_account_id
from finlabs_cli.ui.console import console
from finlabs_cli.ui.prompts import choose, confirm, secret, text
from finlabs_cli.ui.tables import accounts_table, account_summary

accounts_app = typer.Typer(help="Manage broker accounts.")


@accounts_app.command("list")
def list_accounts() -> None:
    """Print registered broker accounts."""
    store = AccountStore.default()
    console.print(accounts_table(store.list()))


@accounts_app.command("register")
def register_account() -> None:
    """Register an account using interactive prompts."""
    broker = choose(
        "Broker",
        choices=[("KIS", "kis"), ("Kiwoom", "kiwoom"), ("Toss", "toss")],
    )
    alias = text("Account Alias")
    owner_name = text("Owner Name")
    environment = _environment_prompt(broker)
    expires_at = text("Expired At (YYYY-MM-DD)", default=date.today().isoformat())
    account_number = ""
    account_password = ""
    credentials: dict[str, str] = {}

    if broker == "kis":
        account_number = text("Account Number")
        credentials["app_key"] = secret("API Key")
        credentials["app_secret"] = secret("Secret Key")
    elif broker == "kiwoom":
        credentials["app_key"] = secret("API Key")
        credentials["secret_key"] = secret("Secret Key")
    else:
        credentials["client_id"] = secret("Client ID")
        credentials["client_secret"] = secret("Client Secret")

    if confirm("Store account password? Not needed for chart/realtime.", default=False):
        account_password = secret("Account Password")

    account = Account(
        id=new_account_id(),
        alias=alias,
        broker=broker,  # type: ignore[arg-type]
        owner_name=owner_name,
        environment=environment,
        expires_at=expires_at,
        account_number=account_number,
        account_password=account_password,
        credentials=credentials,
    )
    store = AccountStore.default()
    store.add(account)
    console.print(account_summary(account, title="Registered Account"))


@accounts_app.command("update")
def update_account(alias: str | None = typer.Option(None, "--alias")) -> None:
    """Update mutable account fields."""
    store = AccountStore.default()
    account = store.require(alias or _choose_account(store))
    field = choose(
        "Field to update",
        choices=[
            ("Account Alias", "alias"),
            ("Owner Name", "owner_name"),
            ("Account Number", "account_number"),
            ("Account Password", "account_password"),
            ("API Key / Client ID", "api_key"),
            ("Secret Key", "secret_key"),
            ("Expired At", "expires_at"),
        ],
    )
    updated = account
    if field == "alias":
        updated = account.with_changes(alias=text("New Account Alias", default=account.alias))
    elif field == "owner_name":
        updated = account.with_changes(
            owner_name=text("Owner Name", default=account.owner_name)
        )
    elif field == "account_number":
        updated = account.with_changes(
            account_number=text("Account Number", default=account.account_number)
        )
    elif field == "account_password":
        updated = account.with_changes(account_password=secret("Account Password"))
    elif field == "expires_at":
        updated = account.with_changes(
            expires_at=text("Expired At", default=account.expires_at)
        )
    elif field == "api_key":
        key = "client_id" if account.broker == "toss" else "app_key"
        updated = account.with_credential(key, secret("API Key / Client ID"))
    elif field == "secret_key":
        key = "client_secret" if account.broker == "toss" else (
            "secret_key" if account.broker == "kiwoom" else "app_secret"
        )
        updated = account.with_credential(key, secret("Secret Key"))
    store.update(account.alias, updated)
    console.print(account_summary(updated, title="Updated Account"))


@accounts_app.command("delete")
def delete_account(alias: str | None = typer.Option(None, "--alias")) -> None:
    """Delete a registered account after confirmation."""
    store = AccountStore.default()
    account = store.require(alias or _choose_account(store))
    console.print(account_summary(account, title="Delete Account"))
    if not confirm(f"Delete account '{account.alias}'?", default=False):
        raise typer.Exit(code=1)
    store.delete(account.alias)
    console.print(f"[green]Deleted[/green] {account.alias}")


def _choose_account(store: AccountStore) -> str:
    accounts = store.list()
    if not accounts:
        raise typer.BadParameter("no accounts registered")
    return choose("Account", choices=[(account.alias, account.alias) for account in accounts])


def _environment_prompt(broker: str) -> str:
    if broker == "kiwoom":
        choices = [("real", "real"), ("mock", "mock"), ("dev", "dev")]
    else:
        choices = [("real", "real"), ("mock", "mock")]
    return choose("Environment", choices=choices)
