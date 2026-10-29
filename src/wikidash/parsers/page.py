"""Metadata scraped from a rendered Wikidot page."""

import re
from urllib.parse import unquote

from wikidash.models import PageInfo

from .html import attr, parse_page

_PAGE_ID = re.compile(r"WIKIREQUEST\.info\.pageId\s*=\s*(\d+);", re.IGNORECASE)
_FORUM_THREAD = re.compile(r"forum/t-(\d+)")
# Tag links end in '#pages' on some wikis and not on others.
_TAG = re.compile(r"/tag/(\S+?)(?:#pages)?$", re.IGNORECASE)


def parse_page_info(html: str) -> PageInfo:
    soup = parse_page(html)
    info = PageInfo()

    for script in soup.select("head script"):
        match = _PAGE_ID.search(script.get_text())
        if match:
            info.page_id = int(match.group(1))

    rating = soup.select_one("span.rate-points span.number")
    if rating is not None:
        info.rating = _to_int(rating.get_text())

    discuss = _FORUM_THREAD.search(attr(soup.select_one("#discuss-button"), "href") or "")
    if discuss:
        info.forum_thread = int(discuss.group(1))

    tags_box = soup.select_one("div.page-tags")
    tags_span = tags_box.find("span") if tags_box is not None else None
    for link in tags_span.find_all("a") if tags_span is not None else []:
        match = _TAG.search(attr(link, "href") or "")
        if match:
            info.tags.append(unquote(match.group(1)))

    title = soup.select_one("div#page-title")
    if title is not None:
        info.title = title.get_text().strip()

    breadcrumbs = soup.select("div#main-content div#breadcrumbs a")
    if breadcrumbs:
        href = attr(breadcrumbs[-1], "href")
        info.parent = href[1:] if href else None
    return info


def _to_int(text: str) -> int | None:
    try:
        return int(text.strip())
    except ValueError:
        return None
