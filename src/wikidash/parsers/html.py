"""Small helpers over BeautifulSoup shared by all parsers."""

import re

from bs4 import BeautifulSoup, Tag

_DIGITS = re.compile(r"\d+")
_TIME_CLASS = re.compile(r"time_(\d+)")


def parse_fragment(html: str) -> BeautifulSoup:
    """Parse an ajax module body; keeps the top-level structure intact."""
    return BeautifulSoup(html, "html.parser")


def parse_page(html: str) -> BeautifulSoup:
    """Parse a full page (faster lxml parser)."""
    return BeautifulSoup(html, "lxml")


def attr(tag: Tag | None, name: str) -> str | None:
    """Attribute as a plain string (bs4 returns a list for multi-valued ones)."""
    if tag is None:
        return None
    value = tag.get(name)
    if value is None:
        return None
    return " ".join(value) if isinstance(value, list) else value


def first_int(text: str | None) -> int | None:
    """First run of digits in `text`."""
    match = _DIGITS.search(text or "")
    return int(match.group()) if match else None


def timestamp(tag: Tag | None) -> int | None:
    """Unix time from Wikidot's `<span class="odate time_1234567890">`."""
    match = _TIME_CLASS.search(attr(tag, "class") or "")
    return int(match.group(1)) if match else None


def child_tags(tag: Tag) -> list[Tag]:
    return [child for child in tag.children if isinstance(child, Tag)]
