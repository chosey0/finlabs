"""EndpointSpec registry for `[국내주식] 업종_기타.xlsx`."""

from __future__ import annotations

from kis.endpoints.registry import EndpointSpec, register

# Each tuple keeps the source workbook row API 명 in the final field.
_SPECS = (
    (
        "domestic.sector.inquire_index_price",
        "/uapi/domestic-stock/v1/quotations/inquire-index-price",
        "FHPUP02100000",
        None,
        ("FID_INPUT_ISCD",),
        "국내업종 현재지수",
    ),
    (
        "domestic.sector.inquire_index_daily_price",
        "/uapi/domestic-stock/v1/quotations/inquire-index-daily-price",
        "FHPUP02120000",
        None,
        ("FID_COND_MRKT_DIV_CODE", "FID_INPUT_ISCD", "FID_INPUT_DATE_1"),
        "국내업종 일자별지수",
    ),
    (
        "domestic.sector.inquire_index_tickprice",
        "/uapi/domestic-stock/v1/quotations/inquire-index-tickprice",
        "FHPUP02110100",
        None,
        ("FID_COND_MRKT_DIV_CODE",),
        "국내업종 시간별지수(초)",
    ),
    (
        "domestic.sector.inquire_index_timeprice",
        "/uapi/domestic-stock/v1/quotations/inquire-index-timeprice",
        "FHPUP02110200",
        None,
        ("FID_INPUT_ISCD", "FID_COND_MRKT_DIV_CODE"),
        "국내업종 시간별지수(분)",
    ),
    (
        "domestic.sector.inquire_time_indexchartprice",
        "/uapi/domestic-stock/v1/quotations/inquire-time-indexchartprice",
        "FHKUP03500200",
        None,
        (
            "FID_ETC_CLS_CODE",
            "FID_INPUT_ISCD",
            "FID_INPUT_HOUR_1",
            "FID_PW_DATA_INCU_YN",
        ),
        "업종 분봉조회",
    ),
    (
        "domestic.sector.inquire_daily_indexchartprice",
        "/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice",
        "FHKUP03500100",
        "FHKUP03500100",
        (
            "FID_INPUT_ISCD",
            "FID_INPUT_DATE_1",
            "FID_INPUT_DATE_2",
            "FID_PERIOD_DIV_CODE",
        ),
        "국내주식업종기간별시세(일/주/월/년)",
    ),
    (
        "domestic.sector.inquire_index_category_price",
        "/uapi/domestic-stock/v1/quotations/inquire-index-category-price",
        "FHPUP02140000",
        None,
        (
            "FID_INPUT_ISCD",
            "FID_COND_SCR_DIV_CODE",
            "FID_MRKT_CLS_CODE",
            "FID_BLNG_CLS_CODE",
        ),
        "국내업종 구분별전체시세",
    ),
    (
        "domestic.sector.exp_index_trend",
        "/uapi/domestic-stock/v1/quotations/exp-index-trend",
        "FHPST01840000",
        None,
        ("FID_INPUT_HOUR_1", "FID_INPUT_ISCD", "FID_COND_MRKT_DIV_CODE"),
        "국내주식 예상체결지수 추이",
    ),
    (
        "domestic.sector.exp_total_index",
        "/uapi/domestic-stock/v1/quotations/exp-total-index",
        "FHKUP11750000",
        None,
        (
            "fid_cond_mrkt_div_code",
            "fid_cond_scr_div_code",
            "fid_input_iscd",
            "fid_mkop_cls_code",
        ),
        "국내주식 예상체결 전체지수",
    ),
    (
        "domestic.sector.inquire_vi_status",
        "/uapi/domestic-stock/v1/quotations/inquire-vi-status",
        "FHPST01390000",
        None,
        (
            "FID_COND_SCR_DIV_CODE",
            "FID_MRKT_CLS_CODE",
            "FID_INPUT_ISCD",
            "FID_RANK_SORT_CLS_CODE",
            "FID_INPUT_DATE_1",
            "FID_TRGT_CLS_CODE",
            "FID_TRGT_EXLS_CLS_CODE",
        ),
        "변동성완화장치(VI) 현황",
    ),
    (
        "domestic.sector.comp_interest",
        "/uapi/domestic-stock/v1/quotations/comp-interest",
        "FHPST07020000",
        None,
        ("FID_COND_SCR_DIV_CODE", "FID_DIV_CLS_CODE", "FID_DIV_CLS_CODE1"),
        "금리 종합(국내채권/금리)",
    ),
    (
        "domestic.sector.news_title",
        "/uapi/domestic-stock/v1/quotations/news-title",
        "FHKST01011800",
        None,
        (
            "FID_COND_MRKT_CLS_CODE",
            "FID_INPUT_ISCD",
            "FID_TITL_CNTT",
            "FID_INPUT_DATE_1",
            "FID_INPUT_HOUR_1",
            "FID_RANK_SORT_CLS_CODE",
            "FID_INPUT_SRNO",
        ),
        "종합 시황/공시(제목)",
    ),
    (
        "domestic.sector.chk_holiday",
        "/uapi/domestic-stock/v1/quotations/chk-holiday",
        "CTCA0903R",
        None,
        ("CTX_AREA_NK", "CTX_AREA_FK"),
        "국내휴장일조회",
    ),
    (
        "domestic.sector.market_time",
        "/uapi/domestic-stock/v1/quotations/market-time",
        "HHMCM000002C0",
        None,
        (),
        "국내선물 영업일조회",
    ),
)

for name, path, tr_id_real, tr_id_mock, required_params, _api_name in _SPECS:
    register(
        EndpointSpec(
            name=name,
            method="GET",
            path=path,
            tr_id_real=tr_id_real,
            tr_id_mock=tr_id_mock,
            required_params=required_params,
        )
    )
