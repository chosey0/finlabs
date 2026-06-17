from __future__ import annotations

from modules.brokers.kiwoom.endpoints.registry import EndpointSpec


def build_rest_headers(
    *,
    access_token: str,
    spec: EndpointSpec,
    cont_yn: str = "N",
    next_key: str = "",
) -> dict[str, str]:
    headers = {
        "authorization": f"Bearer {access_token}",
        "api-id": spec.api_id,
        "content-type": "application/json;charset=UTF-8",
        "accept": "application/json",
    }
    if spec.supports_continuation:
        headers["cont-yn"] = cont_yn
        headers["next-key"] = next_key
    return headers


def build_websocket_login_message(*, access_token: str) -> dict[str, str]:
    return {"trnm": "LOGIN", "token": access_token}


def build_websocket_subscription_message(
    *,
    tr_id: str,
    tr_key: str,
    trnm: str = "REG",
    group_no: str = "1",
    refresh: bool = True,
) -> dict[str, object]:
    body: dict[str, object] = {
        "trnm": trnm,
        "grp_no": group_no,
        "data": [{"item": [tr_key], "type": [tr_id]}],
    }
    if trnm == "REG":
        body["refresh"] = "1" if refresh else "0"
    return body
