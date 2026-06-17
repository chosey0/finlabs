"""Persistence operations for canonical market surge events."""

from __future__ import annotations

from collections.abc import Iterable

import duckdb

from modules.domain.surge import SurgeEvent


def create_surge_event_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create the market surge-event dataset table when absent."""

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS surge_events (
            market VARCHAR NOT NULL,
            ticker VARCHAR NOT NULL,
            surge_date DATE NOT NULL,
            close DECIMAL(28, 8) NOT NULL,
            turnover DECIMAL(28, 4) NOT NULL,
            turnover_source VARCHAR NOT NULL,
            return_1d DECIMAL(18, 10) NOT NULL,
            max_return_3d DECIMAL(18, 10) NOT NULL,
            trigger_sessions INTEGER NOT NULL,
            price_source VARCHAR NOT NULL,
            generated_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
            PRIMARY KEY (market, ticker, surge_date)
        )
        """
    )


def upsert_surge_events(
    connection: duckdb.DuckDBPyConnection,
    events: Iterable[SurgeEvent],
) -> int:
    """Idempotently store events by market, ticker, and surge date."""

    create_surge_event_schema(connection)
    rows = list(events)
    if not rows:
        return 0
    connection.execute(
        """
        INSERT INTO surge_events (
            market, ticker, surge_date, close, turnover, turnover_source,
            return_1d, max_return_3d, trigger_sessions, price_source
        )
        SELECT unnest(?), unnest(?), unnest(?), unnest(?), unnest(?),
               unnest(?), unnest(?), unnest(?), unnest(?), unnest(?)
        ON CONFLICT (market, ticker, surge_date) DO UPDATE SET
            close = excluded.close,
            turnover = excluded.turnover,
            turnover_source = excluded.turnover_source,
            return_1d = excluded.return_1d,
            max_return_3d = excluded.max_return_3d,
            trigger_sessions = excluded.trigger_sessions,
            price_source = excluded.price_source,
            generated_at = now()
        """,
        [
            [event.market for event in rows],
            [event.ticker for event in rows],
            [event.surge_date for event in rows],
            [event.close for event in rows],
            [event.turnover for event in rows],
            [event.turnover_source for event in rows],
            [event.return_1d for event in rows],
            [event.max_return_3d for event in rows],
            [event.trigger_sessions for event in rows],
            [event.price_source for event in rows],
        ],
    )
    return len(rows)
