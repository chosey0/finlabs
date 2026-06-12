"""언론사별 기사 본문 선택자 파서를 검증한다."""

from __future__ import annotations

import pytest

from modules.news.articles.parsers import ARTICLE_PARSERS


@pytest.mark.parametrize(
    ("publisher", "html", "expected"),
    [
        (
            "edaily",
            """
            <div>outside</div><div id="contents">
              <section class="position_r center1080">
                <section class="aside_left"><div class="article_news">
                  <div class="newscontainer"><div class="news_body">
                    Edaily <span>body</span><script>ignored()</script>
                  </div></div>
                </div></section>
              </section>
            </div>
            """,
            "Edaily body",
        ),
        (
            "newspim",
            """
            <div id="news-contents"><div>caption</div>
              <p>Newspim first</p><p>second</p>
            </div><p>outside</p>
            """,
            "Newspim first second",
        ),
        (
            "etoday",
            """
            <html><body><div class="wrap"><article>
              <section class="view_body_moduleWrap"><div class="l_content_module">
                <div><div><div class="view_contents"><div class="articleView">
                  <p>Etoday first</p><p>second</p>
                </div></div></div></div>
              </div></section>
            </article></div><p>outside</p></body></html>
            """,
            "Etoday first second",
        ),
        (
            "hankyung",
            """
            <div id="articletxt"><span>caption</span>
              <p>Hankyung <a href="#">linked</a> body</p>
              <div><a href="#">standalone link</a></div>
            </div><p>outside</p>
            """,
            "Hankyung linked body standalone link",
        ),
        (
            "sedaily",
            """
            <div id="article-body"><div>caption</div>
              <section><p>Sedaily first</p><p>second</p></section>
            </div><p>outside</p>
            """,
            "Sedaily first second",
        ),
    ],
)
def test_article_parser_extracts_only_configured_body(
    publisher: str,
    html: str,
    expected: str,
) -> None:
    assert ARTICLE_PARSERS[publisher].parse(html) == expected


def test_article_parser_versions_are_present_and_publisher_specific() -> None:
    # investing.com은 본문이 로그인 장벽 뒤라 본문 수집 registry에 없다
    assert set(ARTICLE_PARSERS) == {
        "edaily",
        "etoday",
        "hankyung",
        "newspim",
        "sedaily",
    }
    versions = {parser.version for parser in ARTICLE_PARSERS.values()}
    assert len(versions) == len(ARTICLE_PARSERS)
    assert all(version.endswith("-v1") for version in versions)


def test_article_parser_rejects_page_without_configured_body() -> None:
    with pytest.raises(ValueError, match="selector produced no visible text"):
        ARTICLE_PARSERS["sedaily"].parse("<html><body>no article body</body></html>")
