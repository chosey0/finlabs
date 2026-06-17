"""Endpoint specs for domestic stock basic quote APIs."""

from __future__ import annotations

from modules.brokers.kis.endpoints.registry import EndpointSpec, register


CHART_MINUTE = register(
    EndpointSpec(
        name="domestic.chart.minute",
        method="GET",
        path="/uapi/domestic-stock/v1/quotations/inquire-time-dailychartprice",
        tr_id_real="FHKST03010230",
        tr_id_mock=None,
        required_params=(
            "FID_COND_MRKT_DIV_CODE",
            "FID_INPUT_ISCD",
            "FID_INPUT_HOUR_1",
            "FID_INPUT_DATE_1",
            "FID_PW_DATA_INCU_YN",
            "FID_FAKE_TICK_INCU_YN",
        ),
        supports_tr_cont=True,
    )
)
