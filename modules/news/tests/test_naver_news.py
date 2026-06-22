"""재사용 가능한 네이버 뉴스 검색 모듈의 공개 계약을 검증한다."""

from __future__ import annotations

import ast
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from modules.news.naver import (
    NaverNewsArticle,
    NaverNewsAuthenticationError,
    NaverNewsIncompleteSearchError,
    NaverNewsMalformedResponseError,
    NaverNewsPermissionError,
    NaverNewsRateLimitError,
    NaverNewsClient,
    NaverNewsUpstreamError,
    NaverNewsValidationError,
)


class FakeResponse:
    def __init__(
        self,
        payload: object,
        *,
        status_code: int = 200,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> object:
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class ScriptedTransport:
    def __init__(self, *responses: FakeResponse | Exception) -> None:
        self.responses = iter(responses)
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, object],
        headers: Mapping[str, str],
    ) -> FakeResponse:
        self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response


def _item(
    published_at: str,
    *,
    title: str = "<b>삼성전자</b> 실적 &amp; 전망",
    original_url: str = "https://publisher.example/article/1",
    naver_url: str = "https://n.news.naver.com/article/1",
) -> dict[str, str]:
    return {
        "title": title,
        "originallink": original_url,
        "link": naver_url,
        "description": "<b>삼성전자</b>가 실적을 발표했다.",
        "pubDate": published_at,
    }


def _page(
    items: list[dict[str, str]],
    *,
    start: int = 1,
    total: int | None = None,
) -> dict[str, object]:
    return {
        "total": len(items) if total is None else total,
        "start": start,
        "display": len(items),
        "items": items,
    }


def test_public_article_is_immutable_and_prefers_original_url() -> None:
    article = NaverNewsArticle(
        title="삼성전자 실적 발표",
        description="분기 실적을 발표했다.",
        published_at=datetime(2026, 6, 19, 9, tzinfo=timezone.utc),
        original_url="https://publisher.example/article/1",
        naver_url="https://n.news.naver.com/article/1",
    )

    assert article.canonical_url == "https://publisher.example/article/1"
    with pytest.raises(AttributeError):
        article.title = "변경"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("client_id", "client_secret", "message"),
    [
        ("", "secret", "client_id"),
        ("client", "", "client_secret"),
    ],
)
def test_client_rejects_blank_credentials(
    client_id: str,
    client_secret: str,
    message: str,
) -> None:
    with pytest.raises(NaverNewsValidationError, match=message):
        NaverNewsClient(client_id, client_secret)


def test_client_representation_does_not_expose_credentials() -> None:
    client = NaverNewsClient(
        "client-id",
        "super-secret",
        transport=ScriptedTransport(),
    )

    representation = repr(client)

    assert "client-id" not in representation
    assert "super-secret" not in representation


def test_search_filters_by_original_offset_date_and_normalizes_markup() -> None:
    transport = ScriptedTransport(
        FakeResponse(
            _page(
                [
                    _item("Fri, 19 Jun 2026 00:30:00 -0700"),
                    _item(
                        "Thu, 18 Jun 2026 23:30:00 -0700",
                        original_url="https://publisher.example/article/2",
                        naver_url="https://n.news.naver.com/article/2",
                    ),
                ]
            )
        )
    )
    client = NaverNewsClient("client", "secret", transport=transport)

    articles = client.search("삼성전자", date(2026, 6, 19))

    assert len(articles) == 1
    assert articles[0].title == "삼성전자 실적 & 전망"
    assert articles[0].published_at.utcoffset().total_seconds() == -7 * 3600
    assert transport.calls[0]["params"] == {
        "query": "삼성전자",
        "display": 100,
        "start": 1,
        "sort": "date",
    }


def test_search_paginates_until_metadata_proves_exhaustion() -> None:
    first_items = [
        _item(
            "Fri, 19 Jun 2026 12:00:00 +0900",
            original_url=f"https://publisher.example/article/{index}",
            naver_url=f"https://n.news.naver.com/article/{index}",
        )
        for index in range(100)
    ]
    transport = ScriptedTransport(
        FakeResponse(_page(first_items, total=101)),
        FakeResponse(
            _page(
                [_item("Thu, 18 Jun 2026 23:59:00 +0900")],
                start=101,
                total=101,
            )
        ),
    )

    articles = NaverNewsClient("client", "secret", transport=transport).search(
        "삼성전자",
        date(2026, 6, 19),
    )

    assert len(articles) == 100
    assert [call["params"]["start"] for call in transport.calls] == [1, 101]


def test_search_does_not_treat_older_local_date_as_cross_offset_exhaustion() -> None:
    first_items = [
        _item(
            "Sat, 20 Jun 2026 12:00:00 +0900",
            original_url=f"https://publisher.example/newer/{index}",
            naver_url=f"https://n.news.naver.com/newer/{index}",
        )
        for index in range(99)
    ]
    first_items.append(
        _item(
            "Thu, 18 Jun 2026 23:30:00 -0700",
            original_url="https://publisher.example/older-local-date",
            naver_url="https://n.news.naver.com/older-local-date",
        )
    )
    transport = ScriptedTransport(
        FakeResponse(_page(first_items, total=101)),
        FakeResponse(
            _page(
                [
                    _item(
                        "Fri, 19 Jun 2026 00:30:00 +0900",
                        original_url="https://publisher.example/target",
                        naver_url="https://n.news.naver.com/target",
                    )
                ],
                start=101,
                total=101,
            )
        ),
    )

    articles = NaverNewsClient("client", "secret", transport=transport).search(
        "삼성전자",
        date(2026, 6, 19),
    )

    assert [article.canonical_url for article in articles] == [
        "https://publisher.example/target"
    ]
    assert [call["params"]["start"] for call in transport.calls] == [1, 101]


def test_search_raises_instead_of_returning_partial_results_at_start_limit() -> None:
    responses = []
    for page_start in range(1, 1000, 100):
        items = [
            _item(
                "Fri, 19 Jun 2026 12:00:00 +0900",
                original_url=f"https://publisher.example/{page_start}/{index}",
                naver_url=f"https://n.news.naver.com/{page_start}/{index}",
            )
            for index in range(100)
        ]
        responses.append(FakeResponse(_page(items, start=page_start, total=2000)))
    final_items = [
        _item(
            "Fri, 19 Jun 2026 12:00:00 +0900",
            original_url=f"https://publisher.example/1000/{index}",
            naver_url=f"https://n.news.naver.com/1000/{index}",
        )
        for index in range(100)
    ]
    responses.append(FakeResponse(_page(final_items, start=1000, total=2000)))

    transport = ScriptedTransport(*responses)
    client = NaverNewsClient(
        "client",
        "secret",
        transport=transport,
    )

    with pytest.raises(NaverNewsIncompleteSearchError):
        client.search("삼성전자", date(2026, 6, 19))

    assert transport.calls[-1]["params"]["start"] == 1000


def test_search_uses_start_1000_when_it_can_prove_completeness() -> None:
    responses = []
    for page_start in range(1, 1000, 100):
        items = [
            _item(
                "Fri, 19 Jun 2026 12:00:00 +0900",
                original_url=f"https://publisher.example/{page_start + index}",
                naver_url=f"https://n.news.naver.com/{page_start + index}",
            )
            for index in range(100)
        ]
        responses.append(FakeResponse(_page(items, start=page_start, total=1001)))
    responses.append(
        FakeResponse(
            _page(
                [
                    _item(
                        "Fri, 19 Jun 2026 12:00:00 +0900",
                        original_url="https://publisher.example/1000",
                        naver_url="https://n.news.naver.com/1000-duplicate",
                    ),
                    _item(
                        "Thu, 18 Jun 2026 23:59:00 +0900",
                        original_url="https://publisher.example/1001",
                        naver_url="https://n.news.naver.com/1001",
                    ),
                ],
                start=1000,
                total=1001,
            )
        )
    )
    transport = ScriptedTransport(*responses)

    articles = NaverNewsClient("client", "secret", transport=transport).search(
        "삼성전자",
        date(2026, 6, 19),
    )

    assert len(articles) == 1000
    assert transport.calls[-1]["params"]["start"] == 1000


def test_search_stops_at_target_date_boundary_for_high_volume_keyword() -> None:
    # A popular keyword reports far more than the pagination cap (total=5000),
    # but once pagination passes the target date's earliest possible instant
    # (its midnight at +14:00) the date is fully covered, so the search completes
    # without hitting the start=1000 limit or raising an incomplete error.
    target_items = [
        _item(
            "Fri, 19 Jun 2026 12:00:00 +0900",
            original_url=f"https://publisher.example/target/{index}",
            naver_url=f"https://n.news.naver.com/target/{index}",
        )
        for index in range(100)
    ]
    older_items = [
        _item(
            "Thu, 18 Jun 2026 09:00:00 +0900",
            original_url=f"https://publisher.example/older/{index}",
            naver_url=f"https://n.news.naver.com/older/{index}",
        )
        for index in range(100)
    ]
    transport = ScriptedTransport(
        FakeResponse(_page(target_items, total=5000)),
        FakeResponse(_page(older_items, start=101, total=5000)),
    )

    articles = NaverNewsClient("client", "secret", transport=transport).search(
        "삼성전자",
        date(2026, 6, 19),
    )

    assert len(articles) == 100
    assert all(article.published_at.date() == date(2026, 6, 19) for article in articles)
    assert [call["params"]["start"] for call in transport.calls] == [1, 101]


def test_search_rejects_short_page_when_metadata_says_results_remain() -> None:
    transport = ScriptedTransport(
        FakeResponse(_page([_item("Fri, 19 Jun 2026 12:00:00 +0900")], total=1000))
    )

    with pytest.raises(NaverNewsMalformedResponseError, match="total result count"):
        NaverNewsClient("client", "secret", transport=transport).search(
            "삼성전자",
            date(2026, 6, 19),
        )


def test_search_retries_rate_limit_with_retry_after_then_succeeds() -> None:
    delays: list[float] = []
    transport = ScriptedTransport(
        FakeResponse({}, status_code=429, headers={"Retry-After": "2"}),
        FakeResponse(_page([])),
    )
    client = NaverNewsClient(
        "client",
        "secret",
        transport=transport,
        sleep=delays.append,
    )

    assert client.search("삼성전자", date(2026, 6, 19)) == ()
    assert delays == [2.0]


def test_search_falls_back_to_configured_delay_for_invalid_retry_after() -> None:
    delays: list[float] = []
    transport = ScriptedTransport(
        FakeResponse({}, status_code=429, headers={"Retry-After": "invalid"}),
        FakeResponse(_page([])),
    )
    client = NaverNewsClient(
        "client",
        "secret",
        transport=transport,
        backoff_seconds=0.25,
        sleep=delays.append,
    )

    assert client.search("삼성전자", date(2026, 6, 19)) == ()
    assert delays == [0.25]


def test_search_reports_exhausted_rate_limit_separately() -> None:
    response = FakeResponse({}, status_code=429)
    client = NaverNewsClient(
        "client",
        "secret",
        transport=ScriptedTransport(response, response),
        max_attempts=2,
        sleep=lambda _: None,
    )

    with pytest.raises(NaverNewsRateLimitError):
        client.search("삼성전자", date(2026, 6, 19))


def test_search_retries_network_failure_without_leaking_exception_details() -> None:
    request = httpx.Request("GET", "https://openapi.naver.com")
    transport = ScriptedTransport(
        httpx.ConnectError("contains-super-secret", request=request),
        httpx.ConnectError("contains-super-secret", request=request),
    )
    client = NaverNewsClient(
        "client",
        "super-secret",
        transport=transport,
        max_attempts=2,
        sleep=lambda _: None,
    )

    with pytest.raises(NaverNewsUpstreamError) as captured:
        client.search("삼성전자", date(2026, 6, 19))

    assert "super-secret" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_search_rejects_malformed_item_instead_of_skipping_it() -> None:
    malformed = _item("not-a-date")
    client = NaverNewsClient(
        "client",
        "secret",
        transport=ScriptedTransport(FakeResponse(_page([malformed]))),
    )

    with pytest.raises(NaverNewsMalformedResponseError):
        client.search("삼성전자", date(2026, 6, 19))


def test_search_deduplicates_by_original_url_and_orders_deterministically() -> None:
    items = [
        _item(
            "Fri, 19 Jun 2026 12:00:00 +0900",
            original_url="https://publisher.example/b",
            naver_url="https://n.news.naver.com/b1",
        ),
        _item(
            "Fri, 19 Jun 2026 12:00:00 +0900",
            original_url="https://publisher.example/a",
            naver_url="https://n.news.naver.com/a",
        ),
        _item(
            "Fri, 19 Jun 2026 11:59:00 +0900",
            original_url="https://publisher.example/b",
            naver_url="https://n.news.naver.com/b2",
        ),
    ]

    result_orders = []
    for ordered_items in (items, list(reversed(items))):
        transport = ScriptedTransport(FakeResponse(_page(ordered_items)))
        articles = NaverNewsClient("client", "secret", transport=transport).search(
            "삼성전자",
            date(2026, 6, 19),
        )
        result_orders.append(articles)

    assert result_orders[0] == result_orders[1]
    assert [article.canonical_url for article in result_orders[0]] == [
        "https://publisher.example/a",
        "https://publisher.example/b",
    ]
    assert result_orders[0][1].naver_url == "https://n.news.naver.com/b1"


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, NaverNewsAuthenticationError),
        (403, NaverNewsPermissionError),
    ],
)
def test_search_does_not_retry_auth_or_permission_failures(
    status_code: int,
    error_type: type[Exception],
) -> None:
    transport = ScriptedTransport(FakeResponse({}, status_code=status_code))
    client = NaverNewsClient("client", "secret", transport=transport)

    with pytest.raises(error_type):
        client.search("삼성전자", date(2026, 6, 19))

    assert len(transport.calls) == 1


def test_search_retries_server_error_then_reports_upstream_failure() -> None:
    delays: list[float] = []
    response = FakeResponse({}, status_code=503)
    client = NaverNewsClient(
        "client",
        "secret",
        transport=ScriptedTransport(response, response, response),
        max_attempts=3,
        backoff_seconds=0.25,
        sleep=delays.append,
    )

    with pytest.raises(NaverNewsUpstreamError):
        client.search("삼성전자", date(2026, 6, 19))

    assert delays == [0.25, 0.5]


@pytest.mark.parametrize(
    "payload",
    [
        ValueError("invalid JSON"),
        [],
        {"total": "1", "start": 1, "display": 1, "items": []},
        {"total": 1, "start": 2, "display": 1, "items": []},
        {"total": 1, "start": 1, "display": 1, "items": ["not-an-object"]},
    ],
)
def test_search_rejects_malformed_response_envelopes(payload: object) -> None:
    client = NaverNewsClient(
        "client",
        "secret",
        transport=ScriptedTransport(FakeResponse(payload)),
    )

    with pytest.raises(NaverNewsMalformedResponseError):
        client.search("삼성전자", date(2026, 6, 19))


def test_credentials_are_sent_only_in_headers() -> None:
    transport = ScriptedTransport(FakeResponse(_page([])))
    client = NaverNewsClient("client-id", "super-secret", transport=transport)

    client.search("삼성전자", date(2026, 6, 19))

    call = transport.calls[0]
    assert call["headers"] == {
        "X-Naver-Client-Id": "client-id",
        "X-Naver-Client-Secret": "super-secret",
    }
    assert "client-id" not in str(call["params"])
    assert "super-secret" not in str(call["params"])


@pytest.mark.parametrize("published_on", ["2026-06-19", datetime(2026, 6, 19)])
def test_search_rejects_non_date_values_before_transport(
    published_on: object,
) -> None:
    transport = ScriptedTransport()
    client = NaverNewsClient("client", "secret", transport=transport)

    with pytest.raises(NaverNewsValidationError, match="datetime.date"):
        client.search("삼성전자", published_on)  # type: ignore[arg-type]

    assert transport.calls == []


def test_search_rejects_blank_keyword_before_transport() -> None:
    transport = ScriptedTransport()
    client = NaverNewsClient("client", "secret", transport=transport)

    with pytest.raises(NaverNewsValidationError, match="keyword"):
        client.search("  ", date(2026, 6, 19))

    assert transport.calls == []


def test_naver_package_has_no_cli_database_or_pipeline_imports() -> None:
    package_dir = Path(__file__).parents[1] / "naver"
    forbidden = {
        "duckdb",
        "modules.news.db",
        "modules.news.main",
        "modules.news.pipeline",
    }

    imports: set[str] = set()
    for path in package_dir.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module)

    assert imports.isdisjoint(forbidden)
