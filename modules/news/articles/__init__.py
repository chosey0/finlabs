"""언론사별 기사 본문 파서 계약과 기본 registry를 제공한다."""

from .parsers import ARTICLE_PARSERS, BaseArticleParser, SelectorArticleParser

__all__ = ["ARTICLE_PARSERS", "BaseArticleParser", "SelectorArticleParser"]
