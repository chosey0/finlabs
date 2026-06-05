from __future__ import annotations

from modules.brokers.kis.config import Credentials
from modules.brokers.kis.types import CustType


def build_rest_headers(
    *,
    credentials: Credentials,
    access_token: str,
    tr_id: str,
    tr_cont: str = "",
    custtype: CustType = "P",
    hashkey: str | None = None,
) -> dict[str, str]:
    """Assemble the common KIS REST request headers."""
    headers: dict[str, str] = {
        "content-type": "application/json; charset=utf-8",
        "authorization": f"Bearer {access_token}",
        "appkey": credentials.app_key,
        "appsecret": credentials.app_secret,
        "tr_id": tr_id,
        "custtype": custtype,
    }
    if tr_cont:
        headers["tr_cont"] = tr_cont
    if hashkey is not None:
        headers["hashkey"] = hashkey
    return headers


def build_websocket_subscribe_message(
    *,
    approval_key: str,
    tr_id: str,
    tr_key: str,
    custtype: CustType = "P",
    tr_type: str = "1",
) -> dict[str, object]:
    """Build a KIS WebSocket subscribe/unsubscribe frame body.

    tr_type "1" = subscribe, "2" = unsubscribe.
    """
    return {
        "header": {
            "approval_key": approval_key,
            "custtype": custtype,
            "tr_type": tr_type,
            "content-type": "utf-8",
        },
        "body": {
            "input": {
                "tr_id": tr_id,
                "tr_key": tr_key,
            }
        },
    }
