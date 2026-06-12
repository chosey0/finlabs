"""EndpointSpec registry for `[국내주식] 실시간시세.xlsx`."""

from __future__ import annotations

from modules.brokers.kis.endpoints.registry import EndpointSpec, register

REALTIME_TRADES = register(
    EndpointSpec(
        name="domestic.realtime.trades",
        method="POST",
        path="/tryitout/H0STCNT0",
        tr_id_real="H0STCNT0",
        tr_id_mock="H0STCNT0",
        required_headers=("approval_key", "custtype", "tr_type", "content-type"),
        required_params=("tr_id", "tr_key"),
    )
)

REALTIME_ORDERBOOK = register(
    EndpointSpec(
        name="domestic.realtime.orderbook",
        method="POST",
        path="/tryitout/H0STASP0",
        tr_id_real="H0STASP0",
        tr_id_mock="H0STASP0",
        required_headers=("approval_key", "custtype", "tr_type", "content-type"),
        required_params=("tr_id", "tr_key"),
    )
)
