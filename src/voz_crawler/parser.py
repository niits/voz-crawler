"""HTML parsing utilities for Voz forum pages."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from parsel import Selector

from .exceptions import PageParsingError

BASE_URL = "https://voz.vn"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PostData:
    """Parsed data for a single forum post."""

    post_id: str
    post_url: str
    datetime: str
    timestamp: int
    username: str
    user_id: int | None
    user_url: str
    user_title: str
    user_banner: str
    avatar_url: str
    content_text: str
    content_html: str
    images: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    reaction_types: list[str] = field(default_factory=list)
    reaction_count: int = 0


@dataclass
class PageData:
    """Parse result for one page of a thread."""

    current_page: int
    total_pages: int
    posts: list[PostData]
    thread_url: str


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Chuẩn hoá Unicode NFC, collapse whitespace, trim."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Post-level parsing
# ---------------------------------------------------------------------------

_POST_ID_RE = re.compile(r"post:\s*(\d+)")
_USER_ID_RE = re.compile(r"\.(\d+)/?$")
_OTHERS_RE = re.compile(r"(\d+)\s+others?")


def _extract_content_with_quotes(article: Selector) -> str:
    """Extract post body text, wrapping quotes in ``<quote>`` tags."""

    body = article.css(".message-body .bbWrapper")
    if not body:
        return ""

    quote_blocks = article.css(".bbCodeBlock--quote")
    replacements: list[str] = []

    for idx, qb in enumerate(quote_blocks):
        author = qb.attrib.get("data-quote", "").strip()
        source_raw = qb.attrib.get("data-source", "")
        quote_post_id = ""
        m = _POST_ID_RE.search(source_raw)
        if m:
            quote_post_id = m.group(1)

        content = qb.css(".bbCodeBlock-expandContent") or qb.css(
            ".bbCodeBlock-content"
        )
        quote_text = (
            normalize_text(" ".join(content.css("::text").getall()))
            if content
            else ""
        )

        attrs: list[str] = []
        if author:
            attrs.append(f'author="{author}"')
        if quote_post_id:
            attrs.append(f'post_id="{quote_post_id}"')
        attr_str = (" " + " ".join(attrs)) if attrs else ""
        replacements.append(f"<quote{attr_str}>{quote_text}</quote>")

    # Replace quote block HTML with placeholders, then extract text
    modified_html = body.get("")
    for idx, qb in enumerate(quote_blocks):
        modified_html = modified_html.replace(
            qb.get(), f"__QUOTE_PLACEHOLDER_{idx}__"
        )

    raw_text = " ".join(Selector(text=modified_html).css("::text").getall())

    for idx, replacement in enumerate(replacements):
        raw_text = raw_text.replace(
            f"__QUOTE_PLACEHOLDER_{idx}__", "\n" + replacement + "\n"
        )

    return normalize_text(raw_text)


def parse_post(article: Selector) -> PostData:
    """Parse a single ``<article class="message">`` into a `PostData`."""

    post_id = article.attrib.get("data-content", "").replace("post-", "")
    post_url_path = article.css(
        "header.message-attribution a[href*=post-]::attr(href)"
    ).get("")
    post_url = BASE_URL + post_url_path if post_url_path else ""

    # Time
    time_el = article.css("time.u-dt")
    post_datetime = time_el.attrib.get("datetime", "") if time_el else ""
    post_timestamp = int(time_el.attrib.get("data-timestamp", 0)) if time_el else 0

    # User
    username = article.attrib.get("data-author", "")
    user_link = article.css("a.username::attr(href)").get("")
    uid_match = _USER_ID_RE.search(user_link)
    user_id = int(uid_match.group(1)) if uid_match else None
    user_url = BASE_URL + user_link if user_link else ""
    user_title = article.css(".userTitle::text").get("").strip()

    avatar_img = article.css(".message-avatar img")
    avatar_url = avatar_img.attrib.get("src", "") if avatar_img else ""

    user_banner = article.css(".userBanner span::text").get("")

    # Content
    content_text = _extract_content_with_quotes(article)
    body = article.css(".message-body .bbWrapper")
    content_html = body.get("") if body else ""

    # Images (skip emoji / reactions)
    images = [
        img.attrib.get("src", "")
        for img in (body.css("img") if body else [])
        if img.attrib.get("src", "")
        and "smilies" not in img.attrib["src"]
        and "reactions" not in img.attrib["src"]
    ]

    # Links
    links = [
        a.attrib["href"]
        for a in (body.css("a.link") if body else [])
        if a.attrib.get("href")
    ]

    # Reactions
    reaction_types: list[str] = []
    reaction_bar = article.css(".reactionsBar")
    if reaction_bar:
        for react in reaction_bar.css(".reaction img"):
            rtype = react.attrib.get("alt", "") or react.attrib.get("title", "")
            if rtype and rtype not in reaction_types:
                reaction_types.append(rtype)

    react_count_text = (
        reaction_bar.css(".reactionsBar-link::text").get("") if reaction_bar else ""
    )
    named_users = (
        reaction_bar.css(".reactionsBar-link bdi::text").getall()
        if reaction_bar
        else []
    )
    others_match = _OTHERS_RE.search(react_count_text)
    total_reactions = (
        int(others_match.group(1)) + len(named_users) if others_match else len(named_users)
    )

    return PostData(
        post_id=post_id,
        post_url=post_url,
        datetime=post_datetime,
        timestamp=post_timestamp,
        username=username,
        user_id=user_id,
        user_url=user_url,
        user_title=user_title,
        user_banner=user_banner,
        avatar_url=avatar_url,
        content_text=content_text,
        content_html=content_html,
        images=images,
        links=links,
        reaction_types=reaction_types,
        reaction_count=total_reactions,
    )


# ---------------------------------------------------------------------------
# Page-level parsing
# ---------------------------------------------------------------------------


def parse_pagination(sel: Selector) -> tuple[int, int]:
    """Return ``(current_page, total_pages)`` from a page selector.

    Returns ``(1, 1)`` when no pagination bar exists (single-page thread).
    """
    page_nav = sel.css("ul.pageNav-main")
    if not page_nav:
        return 1, 1

    current = page_nav.css("li.pageNav-page--current a::text").get("")
    last = page_nav.css("li:last-child a::text").get("")

    try:
        current_page = int(current)
    except (ValueError, TypeError):
        current_page = 1
    try:
        total_pages = int(last)
    except (ValueError, TypeError):
        total_pages = current_page

    return current_page, total_pages


def parse_thread_page(html: str, *, thread_url: str = "") -> PageData:
    """Parse the full HTML of one thread page into `PageData`.

    Raises
    ------
    PageParsingError
        If no posts can be found in the HTML.
    """
    sel = Selector(text=html)
    articles = sel.css("article.message")

    if not articles:
        raise PageParsingError(thread_url, "No posts found on page")

    current_page, total_pages = parse_pagination(sel)
    posts = [parse_post(a) for a in articles]

    return PageData(
        current_page=current_page,
        total_pages=total_pages,
        posts=posts,
        thread_url=thread_url,
    )
