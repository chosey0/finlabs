from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from platformdirs import user_config_dir

from finlabs_cli.models.account import Account


class AccountStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @classmethod
    def default(cls) -> "AccountStore":
        return cls(Path(user_config_dir("finlabs-cli", "finlabs")) / "accounts.json")

    def list(self) -> list[Account]:
        return sorted(self._read().values(), key=lambda account: account.alias)

    def require(self, alias: str) -> Account:
        accounts = self._read()
        try:
            return accounts[alias]
        except KeyError as exc:
            raise ValueError(f"account '{alias}' not found") from exc

    def add(self, account: Account) -> None:
        accounts = self._read()
        if account.alias in accounts:
            raise ValueError(f"account '{account.alias}' already exists")
        accounts[account.alias] = account
        self._write(accounts)

    def update(self, old_alias: str, account: Account) -> None:
        accounts = self._read()
        if old_alias not in accounts:
            raise ValueError(f"account '{old_alias}' not found")
        if old_alias != account.alias and account.alias in accounts:
            raise ValueError(f"account '{account.alias}' already exists")
        accounts.pop(old_alias)
        accounts[account.alias] = account
        self._write(accounts)

    def delete(self, alias: str) -> None:
        accounts = self._read()
        if alias not in accounts:
            raise ValueError(f"account '{alias}' not found")
        accounts.pop(alias)
        self._write(accounts)

    def _read(self) -> dict[str, Account]:
        if not self.path.exists():
            return {}
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        rows = payload.get("accounts", [])
        if not isinstance(rows, list):
            raise ValueError("accounts.json field `accounts` must be a list")
        accounts = [Account.from_dict(row) for row in rows if isinstance(row, dict)]
        return {account.alias: account for account in accounts}

    def _write(self, accounts: dict[str, Account]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "accounts": [asdict(account) for account in sorted(accounts.values(), key=lambda item: item.alias)],
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.chmod(self.path, 0o600)
