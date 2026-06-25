"""종목 마스터 기반 entity 추출과 이벤트 taxonomy DTO의 회귀 동작을 검증한다."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import psycopg
import pytest

from modules.news.db.sql import (
    create_rss_item,
    insert_article,
    list_article_entities,
    replace_symbol_snapshots,
)
from modules.news.entities import (
    ALIAS_MATCH_CONFIDENCE,
    NAME_MATCH_CONFIDENCE,
    build_symbol_lexicon,
    match_stock_entities,
)
from modules.news.pipeline import (
    ENTITY_EXTRACTOR_VERSION,
    OperationResult,
    extract_entities,
)
from modules.news.schema.article import CanonicalArticle, make_content_hash
from modules.news.schema.entity import ArticleEntity
from modules.news.schema.event import (
    EVENT_TAXONOMY,
    NOISE_EVENT_TYPES,
    TAXONOMY_VERSION,
    ArticleEvent,
)
from modules.news.schema.symbol import NewsSymbol
from modules.news.rss.models import CanonicalRssEntry, make_rss_item_id


SEOUL = ZoneInfo("Asia/Seoul")
SYMBOLS = (
    ("삼성전자", "005930"),
    ("SK하이닉스", "000660"),
    ("한화", "000880"),
    ("한화솔루션", "009830"),
)


def _store_symbol_master(connection: psycopg.Connection) -> None:
    replace_symbol_snapshots(
        connection,
        [
            NewsSymbol(
                market="KOSPI",
                symbol=ticker,
                korean_name=name,
                downloaded_at="2026-06-13T00:00:00+09:00",
            )
            for name, ticker in SYMBOLS
        ],
    )


def _store_article(
    connection: psycopg.Connection,
    *,
    url: str,
    title: str,
    content: str,
) -> str:
    item_id = make_rss_item_id(url)
    create_rss_item(
        connection,
        CanonicalRssEntry(
            id=item_id,
            publisher="investing.com",
            url=url,
            title=title,
            author=None,
            summary=None,
            published_at=datetime(2026, 6, 12, 9, 0, tzinfo=SEOUL),
        ),
    )
    insert_article(
        connection,
        CanonicalArticle(
            rss_item_id=item_id,
            content=content,
            content_hash=make_content_hash(content),
            parser_version="investing-article-body-v1",
        ),
    )
    return item_id


def test_lexicon_orders_longest_surface_first_and_includes_aliases():
    lexicon = build_symbol_lexicon(SYMBOLS)

    surfaces = [entry.surface for entry in lexicon]
    assert surfaces.index("한화솔루션") < surfaces.index("한화")
    assert "삼전" in surfaces
    alias = next(entry for entry in lexicon if entry.surface == "삼전")
    assert alias.canonical_name == "삼성전자"
    assert alias.ticker == "005930"
    assert alias.confidence == ALIAS_MATCH_CONFIDENCE


def test_lexicon_skips_blank_and_single_character_names():
    lexicon = build_symbol_lexicon(
        [("", "000001"), ("A", "000002"), ("쏘카", "403550")]
    )

    assert [entry.surface for entry in lexicon] == ["쏘카"]


def test_longer_company_name_consumes_span_of_embedded_shorter_name():
    lexicon = build_symbol_lexicon(SYMBOLS)

    matches = match_stock_entities("한화솔루션, 태양광 모듈 공급 계약", lexicon)
    assert [(m.canonical_name, m.ticker) for m in matches] == [("한화솔루션", "009830")]

    both = match_stock_entities("한화솔루션과 한화가 동반 상승", lexicon)
    assert {(m.canonical_name, m.ticker) for m in both} == {
        ("한화솔루션", "009830"),
        ("한화", "000880"),
    }


def test_alias_match_reports_canonical_name_with_lower_confidence():
    lexicon = build_symbol_lexicon(SYMBOLS)

    matches = match_stock_entities("삼전, 신고가 경신", lexicon)
    assert len(matches) == 1
    assert matches[0].canonical_name == "삼성전자"
    assert matches[0].confidence == ALIAS_MATCH_CONFIDENCE

    mixed = match_stock_entities("삼성전자(삼전), 신고가 경신", lexicon)
    assert len(mixed) == 1
    assert mixed[0].confidence == NAME_MATCH_CONFIDENCE


def test_extract_entities_persists_and_reruns_idempotently(news_connection):
    connection = news_connection
    _store_symbol_master(connection)
    item_id = _store_article(
        connection,
        url="https://kr.investing.com/news/entity-1",
        title="삼성전자, HBM 공급 확대",
        content="삼성전자가 SK하이닉스와 경쟁한다.",
    )

    first = extract_entities(connection)
    second = extract_entities(connection)

    assert first == OperationResult(processed=1, created=1, skipped=0)
    assert second == OperationResult(processed=0, created=0, skipped=0)
    entities = list_article_entities(connection, item_id)
    assert set(entities) == {
        ArticleEntity(
            rss_item_id=item_id,
            entity_type="stock",
            entity_name="삼성전자",
            ticker="005930",
            confidence=NAME_MATCH_CONFIDENCE,
        ),
        ArticleEntity(
            rss_item_id=item_id,
            entity_type="stock",
            entity_name="SK하이닉스",
            ticker="000660",
            confidence=NAME_MATCH_CONFIDENCE,
        ),
    }


def test_extract_entities_records_zero_entity_articles_as_processed(news_connection):
    connection = news_connection
    _store_symbol_master(connection)
    _store_article(
        connection,
        url="https://kr.investing.com/news/entity-2",
        title="코스피 시황",
        content="지수가 보합으로 마감했다.",
    )

    first = extract_entities(connection)
    second = extract_entities(connection)

    assert first == OperationResult(processed=1, created=0, skipped=1)
    assert second == OperationResult(processed=0, created=0, skipped=0)


def test_extract_entities_reprocesses_on_content_or_version_change(news_connection):
    connection = news_connection
    _store_symbol_master(connection)
    item_id = _store_article(
        connection,
        url="https://kr.investing.com/news/entity-3",
        title="시황",
        content="특이사항 없음.",
    )
    assert extract_entities(connection).processed == 1

    new_content = "한화솔루션이 공급 계약을 체결했다."
    insert_article(
        connection,
        CanonicalArticle(
            rss_item_id=item_id,
            content=new_content,
            content_hash=make_content_hash(new_content),
            parser_version="investing-article-body-v1",
        ),
    )
    after_content_change = extract_entities(connection)
    assert after_content_change == OperationResult(processed=1, created=1, skipped=0)
    assert [entity.ticker for entity in list_article_entities(connection, item_id)] == [
        "009830"
    ]

    after_version_bump = extract_entities(
        connection,
        extractor_version=f"{ENTITY_EXTRACTOR_VERSION}-next",
    )
    assert after_version_bump.processed == 1


def test_extract_entities_requires_symbol_master(news_connection):
    connection = news_connection
    _store_article(
        connection,
        url="https://kr.investing.com/news/entity-4",
        title="제목",
        content="본문",
    )

    with pytest.raises(ValueError, match="update-symbols"):
        extract_entities(connection)


def test_extract_entities_reports_pending_and_item_progress(news_connection):
    connection = news_connection
    _store_symbol_master(connection)
    _store_article(
        connection,
        url="https://example.com/entity-progress-1",
        title="삼성전자 진행 상황",
        content="삼성전자 공급 확대",
    )
    _store_article(
        connection,
        url="https://example.com/entity-progress-2",
        title="시장 진행 상황",
        content="특이사항 없음",
    )
    pending_batches = []
    item_results = []

    result = extract_entities(
        connection,
        on_pending=pending_batches.append,
        on_item_result=lambda article, title, item_result: item_results.append(
            (article.rss_item_id, title, item_result.created)
        ),
    )

    assert result == OperationResult(processed=2, created=1, skipped=1)
    assert len(pending_batches) == 1
    assert len(pending_batches[0]) == 2
    assert {title for _, title, _ in item_results} == {
        "삼성전자 진행 상황",
        "시장 진행 상황",
    }


def test_extract_entities_all_processes_every_pending_article(news_connection):
    connection = news_connection
    _store_symbol_master(connection)
    for index in range(105):
        _store_article(
            connection,
            url=f"https://example.com/entity-all-{index}",
            title=f"삼성전자 기사 {index}",
            content="삼성전자 공급 확대",
        )

    result = extract_entities(connection, limit=None)

    assert result == OperationResult(processed=105, created=105, skipped=0)


@pytest.mark.parametrize(
    ("extra_args", "expected_limit"),
    [([], 100), (["--limit", "7"], 7), (["--all"], None)],
)
def test_extract_entities_cli_passes_dsn_and_limit_to_progress_flow(
    monkeypatch,
    extra_args,
    expected_limit,
):
    from typer.testing import CliRunner

    from modules.news import main as news_main

    calls = []
    monkeypatch.setattr(
        news_main,
        "_extract_entities_with_progress",
        lambda dsn, limit: calls.append((dsn, limit)),
    )
    dsn = "postgresql://example/news"

    result = CliRunner().invoke(
        news_main.app,
        ["extract-entities", "--dsn", dsn, *extra_args],
    )

    assert result.exit_code == 0
    assert calls == [(dsn, expected_limit)]


def test_event_taxonomy_is_closed_and_versioned():
    assert len(EVENT_TAXONOMY) == 16
    assert set(NOISE_EVENT_TYPES) <= set(EVENT_TAXONOMY)
    assert TAXONOMY_VERSION == "v1"


def test_article_event_accepts_taxonomy_value_and_defaults_version():
    event = ArticleEvent(
        rss_item_id="a" * 64,
        event_type="contract_supply",
        entities=("삼성전자", "엔비디아"),
        tickers=("005930",),
        industry="semiconductor",
        specificity="low",
        confidence=0.92,
        reason="HBM 공급 확대 계약 보도",
        label_model="claude-haiku-4-5-20251001",
        prompt_version="p1",
    )

    assert event.taxonomy_version == TAXONOMY_VERSION


@pytest.mark.parametrize(
    "override",
    [
        {"event_type": "supply deal"},
        {"confidence": 1.5},
        {"confidence": -0.1},
        {"specificity": "medium"},
        {"label_model": " "},
        {"prompt_version": ""},
    ],
)
def test_article_event_rejects_values_outside_contract(override):
    base = {
        "rss_item_id": "a" * 64,
        "event_type": "earnings",
        "entities": (),
        "tickers": (),
        "industry": "software",
        "specificity": None,
        "confidence": 0.5,
        "reason": "실적 발표",
        "label_model": "m",
        "prompt_version": "p1",
    }

    with pytest.raises(ValueError):
        ArticleEvent(**{**base, **override})
