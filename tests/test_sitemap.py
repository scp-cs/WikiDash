import httpx

from wikidash.http import HttpClient
from wikidash.sitemap import fetch_sitemap, page_name_from_url, parse_lastmod, removed_pages

WIKI = "https://test.wikidot.com"

INDEX = """<?xml version="1.0"?><sitemapindex>
<sitemap><loc>https://test.wikidot.com/sitemap_page_1.xml</loc></sitemap>
<sitemap><loc>https://test.wikidot.com/sitemap_other.xml</loc></sitemap>
</sitemapindex>"""

PAGE_1 = """<?xml version="1.0"?><urlset>
<url><loc>https://test.wikidot.com/scp-001</loc><lastmod>2024-01-02T03:04:05+00:00</lastmod></url>
<url><loc>https://test.wikidot.com/forum/t-1/x</loc></url>
<url><loc>https://test.wikidot.com/</loc></url>
<url><loc>https://test.wikidot.com/secret</loc></url>
<url><loc>https://custom.example/tales:one</loc></url>
</urlset>"""


def test_fetch_sitemap_follows_sub_sitemaps_and_filters() -> None:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(request.url.path)
        return httpx.Response(200, text=PAGE_1 if "page_1" in request.url.path else INDEX)

    client = HttpClient(transport=httpx.MockTransport(handler))
    pages = fetch_sitemap(client, WIKI, blacklist=["secret"])
    assert pages == {"scp-001": 1704164645000, "tales:one": None}
    assert requested == ["/sitemap.xml", "/sitemap_page_1.xml"]  # sitemap_other.xml is ignored


def test_page_name_from_url() -> None:
    assert page_name_from_url(f"{WIKI}/main", WIKI) == "main"
    assert page_name_from_url(f"{WIKI}/", WIKI) is None
    assert page_name_from_url(f"{WIKI}/forum/c-5", WIKI) is None
    assert page_name_from_url("http://other.net/a:b", WIKI) == "a:b"
    assert page_name_from_url("/relative", WIKI) == "relative"


def test_parse_lastmod_and_removed_pages() -> None:
    assert parse_lastmod("not a date") is None
    assert removed_pages(["a", "b", "c"], ["c", "a"]) == ["b"]
