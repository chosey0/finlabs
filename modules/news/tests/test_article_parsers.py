"""언론사별 기사 본문 선택자 파서를 검증한다."""

from __future__ import annotations

import re

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
    assert all(re.search(r"-v\d+$", version) for version in versions)


def test_hankyung_falls_back_to_container_text_without_paragraphs() -> None:
    """제휴·스포츠 템플릿은 <p> 없이 본문이 컨테이너 직속 텍스트로 들어온다."""

    html = """
    <div id="articletxt">
      <figure class="article-figure">
        <img src="x.jpg" alt="사진">
        <figcaption>사진=제공사</figcaption>
      </figure>
      서교림이 생애 첫 승을 거뒀다.<br/><br/>최종 합계 15언더파를 기록했다.
    </div>
    """

    content = ARTICLE_PARSERS["hankyung"].parse(html)

    assert content == "서교림이 생애 첫 승을 거뒀다. 최종 합계 15언더파를 기록했다."
    assert "사진=제공사" not in content


def test_sedaily_photo_article_falls_back_to_caption_text() -> None:
    """포토 기사는 본문이 사진 설명뿐이므로 설명 텍스트를 본문으로 저장한다."""

    html = """
    <div id="article-body">
      <div class="article-photo-wrap"><figure>
        <img src="x.jpg"><figcaption>공연이 펼쳐지고 있다.</figcaption>
      </figure></div>
      <div class="article-photo-wrap"><figure>
        <img src="y.jpg"><figcaption>관객이 모여 있다.</figcaption>
      </figure></div>
    </div>
    """

    assert (
        ARTICLE_PARSERS["sedaily"].parse(html)
        == "공연이 펼쳐지고 있다. 관객이 모여 있다."
    )


def test_article_parser_rejects_page_without_configured_body() -> None:
    with pytest.raises(ValueError, match="selector produced no visible text"):
        ARTICLE_PARSERS["sedaily"].parse("<html><body>no article body</body></html>")
