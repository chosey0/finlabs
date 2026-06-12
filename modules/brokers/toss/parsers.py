from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from modules.brokers.toss.models import (
    Candle,
    CandlePage,
    CurrentPrice,
    KoreanMarketDetail,
    KrMarketCalendar,
    KrMarketDay,
    KrMarketHours,
    MarketSession,
    StockInfo,
    UsMarketCalendar,
    UsMarketDay,
)
from modules.brokers.toss.types import Currency


def result_list(payload: dict[str, Any]) -> list[dict[str, Any]]:
    result = payload.get("result")
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise ValueError("response result must be a list of objects")
    return result


def parse_current_price(row: dict[str, Any]) -> CurrentPrice:
    return CurrentPrice(
        symbol=_required_text(row, "symbol").upper(),
        timestamp=_optional_datetime(row.get("timestamp")),
        last_price=_required_decimal(row, "lastPrice"),
        currency=_currency(row.get("currency")),
        raw=dict(row),
    )


def parse_candle_page(payload: dict[str, Any], *, symbol: str) -> CandlePage:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("response result must be an object")
    rows = result.get("candles")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("response result.candles must be a list of objects")
    candles = tuple(parse_candle(row, symbol=symbol) for row in rows)
    return CandlePage(
        candles=candles,
        next_before=_optional_datetime(result.get("nextBefore")),
        raw=dict(result),
    )


def parse_candle(row: dict[str, Any], *, symbol: str) -> Candle:
    return Candle(
        symbol=symbol,
        timestamp=_required_datetime(row, "timestamp"),
        open_price=_required_decimal(row, "openPrice"),
        high_price=_required_decimal(row, "highPrice"),
        low_price=_required_decimal(row, "lowPrice"),
        close_price=_required_decimal(row, "closePrice"),
        volume=_required_decimal(row, "volume"),
        currency=_currency(row.get("currency")),
        raw=dict(row),
    )


def parse_stock_info(row: dict[str, Any]) -> StockInfo:
    detail = row.get("koreanMarketDetail")
    return StockInfo(
        symbol=_required_text(row, "symbol").upper(),
        name=_required_text(row, "name"),
        english_name=_required_text(row, "englishName"),
        isin_code=_required_text(row, "isinCode"),
        market=_required_text(row, "market"),
        security_type=_required_text(row, "securityType"),
        is_common_share=_required_bool(row, "isCommonShare"),
        status=_required_text(row, "status"),
        currency=_currency(row.get("currency")),
        list_date=_optional_date(row.get("listDate")),
        delist_date=_optional_date(row.get("delistDate")),
        shares_outstanding=_required_decimal(row, "sharesOutstanding"),
        leverage_factor=_optional_decimal(row.get("leverageFactor")),
        korean_market_detail=(
            _parse_korean_market_detail(detail) if isinstance(detail, dict) else None
        ),
        raw=dict(row),
    )


def parse_kr_market_calendar(payload: dict[str, Any]) -> KrMarketCalendar:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("response result must be an object")
    return KrMarketCalendar(
        today=_parse_kr_market_day(_required_object(result, "today")),
        previous_business_day=_parse_kr_market_day(
            _required_object(result, "previousBusinessDay")
        ),
        next_business_day=_parse_kr_market_day(
            _required_object(result, "nextBusinessDay")
        ),
        raw=dict(result),
    )


def parse_us_market_calendar(payload: dict[str, Any]) -> UsMarketCalendar:
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("response result must be an object")
    return UsMarketCalendar(
        today=_parse_us_market_day(_required_object(result, "today")),
        previous_business_day=_parse_us_market_day(
            _required_object(result, "previousBusinessDay")
        ),
        next_business_day=_parse_us_market_day(
            _required_object(result, "nextBusinessDay")
        ),
        raw=dict(result),
    )


def _parse_kr_market_day(row: dict[str, Any]) -> KrMarketDay:
    integrated = row.get("integrated")
    return KrMarketDay(
        date=_required_date(row, "date"),
        integrated=(
            _parse_kr_market_hours(integrated) if isinstance(integrated, dict) else None
        ),
        raw=dict(row),
    )


def _parse_kr_market_hours(row: dict[str, Any]) -> KrMarketHours:
    return KrMarketHours(
        pre_market=_optional_session(row.get("preMarket")),
        regular_market=_optional_session(row.get("regularMarket")),
        after_market=_optional_session(row.get("afterMarket")),
        raw=dict(row),
    )


def _parse_us_market_day(row: dict[str, Any]) -> UsMarketDay:
    return UsMarketDay(
        date=_required_date(row, "date"),
        day_market=_optional_session(row.get("dayMarket")),
        pre_market=_optional_session(row.get("preMarket")),
        regular_market=_optional_session(row.get("regularMarket")),
        after_market=_optional_session(row.get("afterMarket")),
        raw=dict(row),
    )


def _optional_session(value: Any) -> MarketSession | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("expected session object or null")
    return MarketSession(
        start_time=_required_datetime(value, "startTime"),
        end_time=_required_datetime(value, "endTime"),
        single_price_auction_start_time=_optional_datetime(
            value.get("singlePriceAuctionStartTime")
        ),
        single_price_auction_end_time=_optional_datetime(
            value.get("singlePriceAuctionEndTime")
        ),
        raw=dict(value),
    )


def _parse_korean_market_detail(row: dict[str, Any]) -> KoreanMarketDetail:
    return KoreanMarketDetail(
        liquidation_trading=_required_bool(row, "liquidationTrading"),
        nxt_supported=_required_bool(row, "nxtSupported"),
        krx_trading_suspended=_required_bool(row, "krxTradingSuspended"),
        nxt_trading_suspended=_optional_bool(row.get("nxtTradingSuspended")),
        raw=dict(row),
    )


def _required_object(row: dict[str, Any], key: str) -> dict[str, Any]:
    value = row.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"missing or invalid {key}")
    return value


def _required_text(row: dict[str, Any], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing or invalid {key}")
    return value.strip()


def _required_bool(row: dict[str, Any], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"missing or invalid {key}")
    return value


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError("expected boolean or null")
    return value


def _required_decimal(row: dict[str, Any], key: str) -> Decimal:
    value = _optional_decimal(row.get(key))
    if value is None:
        raise ValueError(f"missing or invalid {key}")
    return value


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"invalid decimal value: {value}") from exc


def _required_datetime(row: dict[str, Any], key: str) -> datetime:
    value = _optional_datetime(row.get(key))
    if value is None:
        raise ValueError(f"missing or invalid {key}")
    return value


def _optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected ISO 8601 datetime string or null")
    return datetime.fromisoformat(value)


def _required_date(row: dict[str, Any], key: str) -> date:
    value = _optional_date(row.get(key))
    if value is None:
        raise ValueError(f"missing or invalid {key}")
    return value


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("expected ISO date string or null")
    return date.fromisoformat(value)


def _currency(value: Any) -> Currency:
    if value not in ("KRW", "USD"):
        raise ValueError(f"unsupported currency: {value}")
    return cast(Currency, value)
