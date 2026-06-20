"""네이버 뉴스 검색 클라이언트의 공개 오류 계층이다."""

from __future__ import annotations


class NaverNewsError(Exception):
    """네이버 뉴스 검색 중 발생한 모든 공개 오류의 기본형이다."""


class NaverNewsValidationError(NaverNewsError, ValueError):
    """호출자가 잘못된 검색 인자를 전달했다."""


class NaverNewsAuthenticationError(NaverNewsError):
    """클라이언트 자격증명이 없거나 유효하지 않다."""


class NaverNewsPermissionError(NaverNewsError):
    """등록된 애플리케이션에 뉴스 검색 권한이 없다."""


class NaverNewsRateLimitError(NaverNewsError):
    """네이버 검색 API 호출 한도를 초과했다."""


class NaverNewsUpstreamError(NaverNewsError):
    """네트워크 또는 네이버 서버의 일시적 오류가 발생했다."""


class NaverNewsMalformedResponseError(NaverNewsError):
    """네이버 응답을 공개 결과 모델로 안전하게 변환할 수 없다."""


class NaverNewsIncompleteSearchError(NaverNewsError):
    """API 조회 한계 때문에 지정 날짜의 완전한 결과를 보장할 수 없다."""
