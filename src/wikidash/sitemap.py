"""The wiki's sitemap: which pages exist and when they last changed."""

import re
from collections.abc import Collection, Iterable
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .http import HttpClient
from .store import read_json, write_json

# page name -> last modification in epoch milliseconds (None: wikidot gave no date,
# so the page is always re-checked).
SiteMap = dict[str, int | None]

_SUB_SITEMAP = re.compile(r"_page_\d+\.xml$")


def fetch_sitemap(
    client: HttpClient, wiki_url: str, blacklist: Collection[str] = ()
) -> SiteMap:
    """Collect all pages from /sitemap.xml and the sub-sitemaps it points to."""
    pages: SiteMap = {}
    pending = [f"{wiki_url}/sitemap.xml"]
    while pending:
        xml = BeautifulSoup(client.get(pending.pop()), "xml")
        pending.extend(
            loc.get_text().strip()
            for loc in xml.select("sitemap loc")
            if _SUB_SITEMAP.search(loc.get_text().strip())
        )
        for entry in xml.select("urlset url"):
            loc = entry.find("loc")
            if loc is None:
                continue
            url = loc.get_text().strip()
            name = page_name_from_url(url, wiki_url)
            if name is None or url in blacklist or name in blacklist:
                continue
            lastmod = entry.find("lastmod")
            pages[name] = parse_lastmod(lastmod.get_text().strip()) if lastmod else None
    return pages


def page_name_from_url(url: str, wiki_url: str) -> str | None:
    """Page name of a sitemap URL; None for the front page and for forum URLs."""
    if url.startswith(wiki_url):
        name = url[len(wiki_url) :]
    elif url.startswith("http"):
        # A custom domain (e.g. scpfoundation.net) that redirects to the wikidot site.
        name = urlparse(url).path
    else:
        name = url
    name = name.removeprefix("/")
    if name == "" or name.startswith("forum/"):
        return None
    return name


def parse_lastmod(text: str) -> int | None:
    try:
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except ValueError:
        return None


def removed_pages(old: Iterable[str], new: Iterable[str]) -> list[str]:
    """Pages present in the previous sitemap but gone from the new one."""
    still_there = set(new)
    return [name for name in old if name not in still_there]


def read_sitemap(path: Path) -> SiteMap | None:
    """The previous sitemap, or None if no run has finished yet."""
    return read_json(path) if path.exists() else None


def write_sitemap(path: Path, sitemap: SiteMap) -> None:
    write_json(path, sitemap)
