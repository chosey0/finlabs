"""EndpointSpec registry for `[해외주식] 기본시세.xlsx`."""

from __future__ import annotations

from modules.brokers.kis.endpoints.registry import EndpointSpec, register

CURRENT_PRICE = register(
    EndpointSpec(
        name="overseas.price.current",
        method="GET",
        path="/uapi/overseas-price/v1/quotations/price",
        tr_id_real="HHDFS00000300",
        tr_id_mock=None,
        required_params=("AUTH", "EXCD", "SYMB"),
    )
)

CHART_OHLCV = register(
    EndpointSpec(
        name="overseas.chart.ohlcv",
        method="GET",
        path="/uapi/overseas-price/v1/quotations/inquire-daily-chartprice",
        tr_id_real="FHKST03030100",
        tr_id_mock=None,
        required_params=(
            "FID_COND_MRKT_DIV_CODE",
            "FID_INPUT_ISCD",
            "FID_INPUT_DATE_1",
            "FID_INPUT_DATE_2",
            "FID_PERIOD_DIV_CODE",
        ),
    )
)

CHART_DAILYPRICE = register(
    EndpointSpec(
        name="overseas.chart.dailyprice",
        method="GET",
        path="/uapi/overseas-price/v1/quotations/dailyprice",
        tr_id_real="HHDFS76240000",
        tr_id_mock=None,
        required_params=("AUTH", "EXCD", "SYMB", "GUBN", "BYMD", "MODP", "KEYB"),
        supports_tr_cont=True,
    )
)

CHART_MINUTE = register(
    EndpointSpec(
        name="overseas.chart.minute",
        method="GET",
        path="/uapi/overseas-price/v1/quotations/inquire-time-itemchartprice",
        tr_id_real="HHDFS76950200",
        tr_id_mock=None,
        required_params=(
            "AUTH",
            "EXCD",
            "SYMB",
            "NMIN",
            "PINC",
            "NEXT",
            "NREC",
            "FILL",
            "KEYB",
        ),
        supports_tr_cont=True,
    )
)
