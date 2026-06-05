"""EndpointSpec registry for `[해외주식] 실시간시세.xlsx`."""

from __future__ import annotations

from modules.brokers.kis.endpoints.registry import EndpointSpec, register

REALTIME_TRADES = register(
    EndpointSpec(
        name="overseas.realtime.trades",
        method="POST",
        path="/tryitout/HDFSCNT0",
        tr_id_real="HDFSCNT0",
        tr_id_mock=None,
        required_headers=("approval_key", "custtype", "tr_type", "content-type"),
        required_params=("tr_id", "tr_key"),
    )
)

REALTIME_ORDERBOOK = register(
    EndpointSpec(
        name="overseas.realtime.orderbook",
        method="POST",
        path="/tryitout/HDFSASP0",
        tr_id_real="HDFSASP0",
        tr_id_mock=None,
        required_headers=("approval_key", "custtype", "tr_type", "content-type"),
        required_params=("tr_id", "tr_key"),
    )
)
