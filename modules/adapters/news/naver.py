"""Adapt the reusable Naver search client to canonical news candidates."""

from __future__ import annotations

from datetime import date

from modules.domain.news_intelligence import (
    NewsArticleCandidate,
    NewsDiscoveryIncompleteError,
    NewsProviderError,
)
from modules.news.naver import (
    NaverNewsClient,
    NaverNewsError,
    NaverNewsIncompleteSearchError,
)


class NaverNewsSearchAdapter:
    def __init__(self, client: NaverNewsClient) -> None:
        self._client = client

    def search_date(
        self,
        *,
        keyword: str,
        provider_date: date,
    ) -> tuple[NewsArticleCandidate, ...]:
        try:
            articles = self._client.search(keyword, provider_date)
        except NaverNewsIncompleteSearchError as error:
            raise NewsDiscoveryIncompleteError(str(error)) from error
        except NaverNewsError as error:
            raise NewsProviderError(str(error)) from error
        return tuple(
            NewsArticleCandidate(
                title=article.title,
                description=article.description,
                published_at=article.published_at,
                original_url=article.original_url,
                naver_url=article.naver_url,
            )
            for article in articles
        )
