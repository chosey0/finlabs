"""Fixture-based tests for the Toss calendar → canonical model adapter."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from modules.adapters.brokers.toss import (
    kr_calendar_to_market_days,
    us_calendar_to_market_days,
)
from modules.brokers.toss.parsers import (
    parse_kr_market_calendar,
    parse_us_market_calendar,
)

KST = timezone(timedelta(hours=9))

KR_PAYLOAD = {
    "result": {
        "today": {"date": "2026-05-05", "integrated": None},
        "previousBusinessDay": {
            "date": "2026-05-04",
            "integrated": {
                "preMarket": {
                    "startTime": "2026-05-04T08:00:00+09:00",
                    "singlePriceAuctionStartTime": "2026-05-04T08:50:00+09:00",
                    "endTime": "2026-05-04T09:00:00+09:00",
                },
                "regularMarket": {
                    "startTime": "2026-05-04T09:00:00+09:00",
                    "singlePriceAuctionStartTime": "2026-05-04T15:20:00+09:00",
                    "endTime": "2026-05-04T15:30:00+09:00",
                },
                "afterMarket": {
                    "startTime": "2026-05-04T15:30:00+09:00",
                    "singlePriceAuctionEndTime": "2026-05-04T15:40:00+09:00",
                    "endTime": "2026-05-04T20:00:00+09:00",
                },
            },
        },
        "nextBusinessDay": {
            "date": "2026-05-06",
            "integrated": {
                "preMarket": None,
                "regularMarket": {
                    "startTime": "2026-05-06T09:00:00+09:00",
                    "singlePriceAuctionStartTime": None,
                    "endTime": "2026-05-06T15:30:00+09:00",
                },
                "afterMarket": None,
            },
        },
    }
}

US_PAYLOAD = {
    "result": {
        "today": {
            "date": "2026-07-03",
            "dayMarket": None,
            "preMarket": None,
            "regularMarket": None,
            "afterMarket": None,
        },
        "previousBusinessDay": {
            "date": "2026-07-02",
            "dayMarket": {
                "startTime": "2026-07-02T09:00:00+09:00",
                "endTime": "2026-07-02T16:50:00+09:00",
            },
            "preMarket": {
                "startTime": "2026-07-02T17:00:00+09:00",
                "endTime": "2026-07-02T22:30:00+09:00",
            },
            "regularMarket": {
                "startTime": "2026-07-02T22:30:00+09:00",
                "endTime": "2026-07-03T05:00:00+09:00",
            },
            "afterMarket": {
                "startTime": "2026-07-03T05:00:00+09:00",
                "endTime": "2026-07-03T07:00:00+09:00",
            },
        },
        "nextBusinessDay": {
            "date": "2026-07-06",
            "dayMarket": {
                "startTime": "2026-07-06T09:00:00+09:00",
                "endTime": "2026-07-06T16:50:00+09:00",
            },
            "preMarket": {
                "startTime": "2026-07-06T17:00:00+09:00",
                "endTime": "2026-07-06T22:30:00+09:00",
            },
            "regularMarket": {
                "startTime": "2026-07-06T22:30:00+09:00",
                "endTime": "2026-07-07T05:00:00+09:00",
            },
            "afterMarket": {
                "startTime": "2026-07-07T05:00:00+09:00",
                "endTime": "2026-07-07T07:00:00+09:00",
            },
        },
    }
}


def test_kr_days_are_chronological_and_holiday_maps_to_closed() -> None:
    days = kr_calendar_to_market_days(parse_kr_market_calendar(KR_PAYLOAD))

    assert [day.date for day in days] == [
        date(2026, 5, 4),
        date(2026, 5, 5),
        date(2026, 5, 6),
    ]
    assert all(day.market == "KR" for day in days)
    holiday = days[1]
    assert holiday.status == "closed"
    assert holiday.sessions == ()


def test_kr_open_day_converts_all_sessions_with_auction_times() -> None:
    days = kr_calendar_to_market_days(parse_kr_market_calendar(KR_PAYLOAD))

    open_day = days[0]
    assert open_day.status == "open"
    assert [session.kind for session in open_day.sessions] == [
        "pre_market",
        "regular",
        "after_market",
    ]
    regular = open_day.sessions[1]
    assert regular.start_at == datetime(2026, 5, 4, 9, tzinfo=KST)
    assert regular.end_at == datetime(2026, 5, 4, 15, 30, tzinfo=KST)
    assert regular.auction_start_at == datetime(2026, 5, 4, 15, 20, tzinfo=KST)
    assert regular.auction_end_at is None
    after = open_day.sessions[2]
    assert after.auction_end_at == datetime(2026, 5, 4, 15, 40, tzinfo=KST)


def test_kr_missing_sessions_are_dropped_not_estimated() -> None:
    days = kr_calendar_to_market_days(parse_kr_market_calendar(KR_PAYLOAD))

    regular_only = days[2]
    assert regular_only.status == "open"
    assert [session.kind for session in regular_only.sessions] == ["regular"]
    assert regular_only.sessions[0].auction_start_at is None


def test_us_full_day_keeps_four_sessions_across_midnight() -> None:
    days = us_calendar_to_market_days(parse_us_market_calendar(US_PAYLOAD))

    assert all(day.market == "US" for day in days)
    full_day = days[0]
    assert full_day.date == date(2026, 7, 2)
    assert full_day.status == "open"
    assert [session.kind for session in full_day.sessions] == [
        "day_market",
        "pre_market",
        "regular",
        "after_market",
    ]
    regular = full_day.sessions[2]
    assert regular.start_at == datetime(2026, 7, 2, 22, 30, tzinfo=KST)
    assert regular.end_at == datetime(2026, 7, 3, 5, tzinfo=KST)
    assert regular.auction_start_at is None


def test_us_holiday_with_explicit_null_sessions_maps_to_closed() -> None:
    days = us_calendar_to_market_days(parse_us_market_calendar(US_PAYLOAD))

    holiday = days[1]
    assert holiday.date == date(2026, 7, 3)
    assert holiday.status == "closed"
    assert holiday.sessions == ()
