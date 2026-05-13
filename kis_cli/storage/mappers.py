from __future__ import annotations

import json

from kis import OhlcvBar, OverseasMinuteBar, SymbolRecord

from kis_cli.utils.time import now_kst_iso


def record_to_db_values(record: SymbolRecord) -> dict[str, object]:
    return {
        "market": record.market,
        "symbol": record.symbol,
        "standard_code": record.standard_code,
        "realtime_symbol": record.realtime_symbol,
        "korean_name": record.korean_name,
        "english_name": record.english_name,
        "security_type": record.security_type,
        "currency": record.currency,
        "exchange_id": record.exchange_id,
        "exchange_code": record.exchange_code,
        "exchange_name": record.exchange_name,
        "country_code": record.country_code,
        "listed_date": record.listed_date,
        "base_price": record.base_price,
        "lot_size": record.lot_size,
        "raw_source": record.raw_source,
        "raw": json.dumps(record.raw, ensure_ascii=False, sort_keys=True),
        "downloaded_at": record.downloaded_at or now_kst_iso(),
    }


def bar_to_db_values(bar: OhlcvBar) -> dict[str, object]:
    return {
        "market": bar.market,
        "symbol": bar.symbol,
        "interval": bar.interval,
        "timestamp": bar.timestamp,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": bar.volume,
        "change": float(bar.change) if bar.change is not None else None,
        "change_rate": float(bar.change_rate) if bar.change_rate is not None else None,
        "amount": float(bar.amount) if bar.amount is not None else None,
    }


def minute_bar_to_db_values(bar: OverseasMinuteBar) -> dict[str, object]:
    return {
        "market": bar.market,
        "symbol": bar.symbol,
        "interval_minutes": bar.interval_minutes,
        "local_business_date": bar.local_business_date,
        "local_date": bar.local_date,
        "local_time": bar.local_time,
        "korea_date": bar.korea_date,
        "korea_time": bar.korea_time,
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": bar.volume,
        "amount": float(bar.amount),
    }
