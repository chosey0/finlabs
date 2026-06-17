from __future__ import annotations

from finlabs_cli.app.token_store import JsonTokenStore
from finlabs_cli.models.account import Account


def build_client(account: Account, token_store: JsonTokenStore):
    if account.broker == "kis":
        from modules.brokers.kis import Credentials, KisClient

        return KisClient(
            credentials=Credentials(
                app_key=account.credentials["app_key"],
                app_secret=account.credentials["app_secret"],
                account_number=account.account_number or None,
            ),
            environment=account.environment,  # type: ignore[arg-type]
            token_cache=token_store.namespaced(account.alias),
        )
    if account.broker == "kiwoom":
        from modules.brokers.kiwoom import Credentials, KiwoomClient

        return KiwoomClient(
            credentials=Credentials(
                app_key=account.credentials["app_key"],
                secret_key=account.credentials["secret_key"],
            ),
            environment=account.environment,  # type: ignore[arg-type]
            token_cache=token_store.namespaced(account.alias),
        )
    if account.broker == "toss":
        from modules.brokers.toss import Credentials, TossClient

        return TossClient(
            credentials=Credentials(
                client_id=account.credentials["client_id"],
                client_secret=account.credentials["client_secret"],
            ),
            token_cache=token_store.namespaced(account.alias),
        )
    raise ValueError(f"unsupported broker: {account.broker}")


async def revoke_token(account: Account, token_store: JsonTokenStore) -> str:
    namespaced = token_store.namespaced(account.alias)
    if account.broker == "kiwoom":
        from modules.brokers.kiwoom import revoke_access_token_async

        token = _first_access_token(namespaced)
        if not token:
            return f"[yellow]No cached token for {account.alias}[/yellow]"
        await revoke_access_token_async(
            environment=account.environment,  # type: ignore[arg-type]
            app_key=account.credentials["app_key"],
            secret_key=account.credentials["secret_key"],
            token=token,
        )
    for key in list(namespaced.records()):
        namespaced.delete(key)
    return f"[green]Token cache cleared[/green] {account.alias}"


def _first_access_token(store: JsonTokenStore) -> str:
    for record in store.records().values():
        if record.access_token:
            return record.access_token
    return ""
