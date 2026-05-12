from __future__ import annotations

SUPABASE_TABLE_NAMES = ("symbols", "ohlcv_bars")

SUPABASE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS symbols (
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    standard_code TEXT,
    realtime_symbol TEXT,
    korean_name TEXT,
    english_name TEXT,
    security_type TEXT,
    currency TEXT,
    exchange_id TEXT,
    exchange_code TEXT,
    exchange_name TEXT,
    country_code TEXT,
    listed_date DATE,
    base_price NUMERIC,
    lot_size BIGINT,
    raw_source TEXT NOT NULL DEFAULT '',
    raw JSONB NOT NULL DEFAULT '{}'::jsonb,
    downloaded_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market, symbol)
);

CREATE INDEX IF NOT EXISTS idx_symbols_symbol
    ON symbols (symbol);

CREATE INDEX IF NOT EXISTS idx_symbols_market_names
    ON symbols (market, korean_name, english_name);

CREATE TABLE IF NOT EXISTS ohlcv_bars (
    market TEXT NOT NULL,
    symbol TEXT NOT NULL,
    interval TEXT NOT NULL,
    trade_date DATE NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume BIGINT NOT NULL,
    change NUMERIC,
    change_rate NUMERIC,
    amount NUMERIC,
    source TEXT NOT NULL DEFAULT 'kis',
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (market, symbol, interval, trade_date)
);

CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_interval_date
    ON ohlcv_bars (symbol, interval, trade_date DESC);

CREATE INDEX IF NOT EXISTS idx_ohlcv_market_symbol_interval_date
    ON ohlcv_bars (market, symbol, interval, trade_date DESC);
""".strip()


def supabase_schema_sql() -> str:
    return SUPABASE_SCHEMA_SQL + "\n"
