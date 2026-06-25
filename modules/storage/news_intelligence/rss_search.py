"""Read RSS items the news pipeline collected, scoped to a discovery window.

The RSS pipeline (``modules.news``) and the news-intelligence labeling store now
share one PostgreSQL database, so a selected-window news search can pull matching
``rss_items`` rows alongside the Naver results. This module only filters by window
and keyword (ILIKE on title/summary); the orchestration layer owns alias→match
mapping and the domain conversion.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

import psycopg


@dataclass(frozen=True, slots=True)
class RssItemRow:
    """A matched ``rss_items`` row. ``published_at`` is the stored Seoul wall clock."""

    url: str
    title: str
    summary: str | None
    published_at: datetime


def search_rss_items(
    connection: psycopg.Connection,
    *,
    window_start: datetime,
    window_end: datetime,
    terms: Sequence[str],
) -> tuple[RssItemRow, ...]:
    """Return RSS items published in ``[window_start, window_end]`` matching a term.

    ``window_start``/``window_end`` are naive Seoul datetimes (matching how the
    pipeline stores ``published_at``). An item matches when any term appears in its
    title or summary, case-insensitively.
    """

    cleaned = [term.strip() for term in terms if term.strip()]
    if not cleaned:
        return ()
    # The RSS pipeline shares this database but may not have run yet (e.g. fresh
    # test schema); without its table there is simply nothing to add.
    if connection.execute("SELECT to_regclass('rss_items')").fetchone()[0] is None:
        return ()
    conditions: list[str] = []
    parameters: list[object] = [window_start, window_end]
    for term in cleaned:
        like = f"%{term}%"
        conditions.append("(title ILIKE %s OR coalesce(summary, '') ILIKE %s)")
        parameters.extend((like, like))
    rows = connection.execute(
        f"""
        SELECT url, title, summary, published_at
        FROM rss_items
        WHERE published_at >= %s AND published_at <= %s
          AND ({" OR ".join(conditions)})
        ORDER BY published_at, url
        """,
        parameters,
    ).fetchall()
    return tuple(
        RssItemRow(
            url=str(row[0]),
            title=str(row[1]),
            summary=None if row[2] is None else str(row[2]),
            published_at=row[3],
        )
        for row in rows
    )
