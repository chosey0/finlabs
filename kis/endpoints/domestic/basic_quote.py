"""EndpointSpec registry for `[국내주식] 기본시세.xlsx`."""

from __future__ import annotations

from kis.endpoints.registry import EndpointSpec, register

CURRENT_PRICE = register(
    EndpointSpec(
        name="domestic.price.current",
        method="GET",
        path="/uapi/domestic-stock/v1/quotations/inquire-price",
        tr_id_real="FHKST01010100",
        tr_id_mock="FHKST01010100",
        required_params=("FID_COND_MRKT_DIV_CODE", "FID_INPUT_ISCD"),
    )
)

CHART_OHLCV = register(
    EndpointSpec(
        name="domestic.chart.ohlcv",
        method="GET",
        path="/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        tr_id_real="FHKST03010100",
        tr_id_mock="FHKST03010100",
        required_params=(
            "FID_COND_MRKT_DIV_CODE",
            "FID_INPUT_ISCD",
            "FID_INPUT_DATE_1",
            "FID_INPUT_DATE_2",
            "FID_PERIOD_DIV_CODE",
            "FID_ORG_ADJ_PRC",
        ),
        supports_tr_cont=True,
    )
)
