"""언론사 HTML에서 정제 기사 본문만 추출한다."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Mapping


@dataclass(slots=True, eq=False)
class _Node:
    tag: str
    attrs: dict[str, str]
    parent: _Node | None = None
    content: list[str | _Node] = field(default_factory=list)

    @property
    def children(self) -> tuple[_Node, ...]:
        return tuple(item for item in self.content if isinstance(item, _Node))


class _DocumentParser(HTMLParser):
    _void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("__document__", {})
        self._stack = [self.root]

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()
        node = _Node(
            normalized_tag,
            {name.lower(): value or "" for name, value in attrs},
            parent=self._stack[-1],
        )
        self._stack[-1].content.append(node)
        if normalized_tag not in self._void_tags:
            self._stack.append(node)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        self.handle_starttag(tag, attrs)
        if self._stack[-1].tag == tag.lower():
            self._stack.pop()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        for index in range(len(self._stack) - 1, 0, -1):
            if self._stack[index].tag == normalized_tag:
                del self._stack[index:]
                return

    def handle_data(self, data: str) -> None:
        self._stack[-1].content.append(data)


@dataclass(frozen=True, slots=True)
class ElementSelector:
    """기사 본문 위치를 표현하는 제한된 CSS 요소 선택자다."""

    tag: str | None = None
    element_id: str | None = None
    classes: frozenset[str] = frozenset()
    nth_child: int | None = None

    def matches(self, node: _Node) -> bool:
        if self.tag is not None and node.tag != self.tag:
            return False
        if self.element_id is not None and node.attrs.get("id") != self.element_id:
            return False
        node_classes = frozenset(node.attrs.get("class", "").split())
        if not self.classes.issubset(node_classes):
            return False
        if self.nth_child is not None:
            if node.parent is None:
                return False
            siblings = node.parent.children
            if siblings.index(node) + 1 != self.nth_child:
                return False
        return True


@dataclass(frozen=True, slots=True)
class SelectorPath:
    """직계 자식 또는 후손 관계로 연결된 요소 선택자 경로다."""

    parts: tuple[ElementSelector, ...]
    direct_children: bool = True

    def matches(self, node: _Node) -> bool:
        if not self.parts or not self.parts[-1].matches(node):
            return False
        if self.direct_children:
            current = node.parent
            for selector in reversed(self.parts[:-1]):
                if current is None or not selector.matches(current):
                    return False
                current = current.parent
            return True

        current = node.parent
        for selector in reversed(self.parts[:-1]):
            while current is not None and not selector.matches(current):
                current = current.parent
            if current is None:
                return False
            current = current.parent
        return True


class BaseArticleParser(ABC):
    """언론사 HTML 본문 파서가 따라야 하는 계약이다."""

    publisher: str
    version: str

    @abstractmethod
    def parse(self, html: str) -> str:
        """HTML에서 정제된 비어 있지 않은 기사 본문을 반환한다."""


@dataclass(frozen=True, slots=True)
class SelectorArticleParser(BaseArticleParser):
    """정해진 선택자에 해당하는 요소의 가시 텍스트만 추출한다.

    일부 언론사는 같은 도메인에서 본문을 ``<p>`` 없이 컨테이너 직속
    텍스트로 내보내는 템플릿을 함께 쓴다. 기본 선택자가 텍스트를 찾지
    못하면 ``fallback_selectors``로 한 번 더 시도하고, ``excluded_tags``
    하위의 텍스트(예: 사진 설명 ``figure``)는 항상 제외한다.
    """

    publisher: str
    version: str
    selectors: tuple[SelectorPath, ...]
    fallback_selectors: tuple[SelectorPath, ...] = ()
    excluded_tags: frozenset[str] = frozenset()

    def parse(self, html: str) -> str:
        document = _DocumentParser()
        document.feed(html)
        for selector_group in (self.selectors, self.fallback_selectors):
            if not selector_group:
                continue
            content = self._extract(document.root, selector_group)
            if content:
                return content
        raise ValueError(
            f"{self.publisher} article body selector produced no visible text"
        )

    def _extract(
        self,
        root: _Node,
        selector_group: tuple[SelectorPath, ...],
    ) -> str:
        selected = [
            node
            for node in _walk(root)
            if any(selector.matches(node) for selector in selector_group)
        ]
        selected_ids = {id(node) for node in selected}
        top_level = [
            node for node in selected if not _has_selected_ancestor(node, selected_ids)
        ]
        return _normalize_text(
            " ".join(
                text
                for node in top_level
                for text in _visible_text(node, excluded=self.excluded_tags)
            )
        )


def _walk(node: _Node):
    for child in node.children:
        yield child
        yield from _walk(child)


def _has_selected_ancestor(node: _Node, selected_ids: set[int]) -> bool:
    current = node.parent
    while current is not None:
        if id(current) in selected_ids:
            return True
        current = current.parent
    return False


def _visible_text(node: _Node, *, excluded: frozenset[str] = frozenset()):
    if node.tag in {"script", "style", "noscript", "svg"} or node.tag in excluded:
        return
    for item in node.content:
        if isinstance(item, str):
            yield item
        else:
            yield from _visible_text(item, excluded=excluded)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _element(
    tag: str | None = None,
    *,
    element_id: str | None = None,
    classes: tuple[str, ...] = (),
    nth_child: int | None = None,
) -> ElementSelector:
    return ElementSelector(tag, element_id, frozenset(classes), nth_child)


# investing.com은 기사 본문이 로그인 장벽 뒤에 있어 본문을 수집하지 않는다.
# RSS 메타데이터(rss_items)만 유지하며, 이 registry에 없는 언론사의 항목은
# collect-articles 대상에서 제외된다.
ARTICLE_PARSERS: Mapping[str, BaseArticleParser] = {
    "edaily": SelectorArticleParser(
        publisher="edaily",
        version="edaily-news-body-v1",
        selectors=(
            SelectorPath(
                (
                    _element(element_id="contents"),
                    _element("section", classes=("center1080", "position_r")),
                    _element("section", classes=("aside_left",)),
                    _element("div", classes=("article_news",)),
                    _element("div", classes=("newscontainer",)),
                    _element("div", classes=("news_body",)),
                )
            ),
        ),
    ),
    "newspim": SelectorArticleParser(
        publisher="newspim",
        version="newspim-news-contents-v1",
        selectors=(
            SelectorPath((_element(element_id="news-contents"), _element("p"))),
        ),
    ),
    "etoday": SelectorArticleParser(
        publisher="etoday",
        version="etoday-article-view-v1",
        selectors=(
            SelectorPath(
                (
                    _element("body"),
                    _element("div", classes=("wrap",)),
                    _element("article"),
                    _element("section", classes=("view_body_moduleWrap",)),
                    _element("div", classes=("l_content_module",)),
                    _element("div"),
                    _element("div"),
                    _element("div", classes=("view_contents",)),
                    _element("div", classes=("articleView",)),
                    _element("p"),
                )
            ),
        ),
    ),
    # 일부 템플릿(제휴·스포츠 기사)은 본문이 <p> 없이 #articletxt 직속
    # 텍스트로 들어오므로 컨테이너 전체를 fallback으로 둔다. 사진 설명은
    # figure 제외로 걸러낸다.
    "hankyung": SelectorArticleParser(
        publisher="hankyung",
        version="hankyung-article-text-v2",
        selectors=(
            SelectorPath(
                (_element(element_id="articletxt"), _element("p")),
                direct_children=False,
            ),
            SelectorPath(
                (_element(element_id="articletxt"), _element("a")),
                direct_children=False,
            ),
        ),
        fallback_selectors=(SelectorPath((_element(element_id="articletxt"),)),),
        excluded_tags=frozenset({"figure"}),
    ),
    # 포토 기사는 본문 텍스트가 사진 설명뿐이므로 컨테이너 전체를
    # fallback으로 두어 설명 텍스트를 본문으로 저장한다.
    "sedaily": SelectorArticleParser(
        publisher="sedaily",
        version="sedaily-article-body-v2",
        selectors=(
            SelectorPath(
                (_element(element_id="article-body"), _element("p")),
                direct_children=False,
            ),
        ),
        fallback_selectors=(SelectorPath((_element(element_id="article-body"),)),),
    ),
}
