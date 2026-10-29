from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from wikidash.ajax import WikidotAjax
from wikidash.api import WikidotApi, paginate
from wikidash.errors import WikidashError
from wikidash.http import HttpClient

WIKI = "https://test.wikidot.com"

ModuleHandler = Callable[[dict[str, str]], dict[str, Any]]


def make_api(modules: dict[str, ModuleHandler], pages: dict[str, str] | None = None) -> WikidotApi:
    """An API wired to a fake Wikidot: ajax modules by name, GET pages by path."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            return httpx.Response(200, json=modules[form["moduleName"]](form))
        if request.url.path == "/system:recent-changes":
            return httpx.Response(200, headers={"Set-Cookie": "wikidot_token7=t; Path=/"})
        return httpx.Response(200, text=(pages or {})[request.url.path])

    client = HttpClient(transport=httpx.MockTransport(handler))
    return WikidotApi(client, WikidotAjax(client, WIKI), WIKI, attempts=2, retry_delay=0)


def revision_row(revision: int) -> str:
    return (
        f"<tr><td>{revision}.</td><td></td><td>S</td>"
        f'<td><a onclick="v({revision + 1000})">v</a></td><td></td>'
        f'<td><span class="odate time_5">d</span></td><td></td></tr>'
    )


def revision_module(total: int, per_page: int = 2) -> ModuleHandler:
    def handle(form: dict[str, str]) -> dict[str, Any]:
        page = int(form["page"])
        newest_first = list(range(total - 1, -1, -1))
        chunk = newest_first[(page - 1) * per_page : page * per_page]
        rows = "".join(revision_row(r) for r in chunk)
        return {"status": "ok", "body": f"<table><tr><th>h</th></tr>{rows}</table>"}

    return handle


def test_paginate_stops_on_empty_page_and_on_condition() -> None:
    pages = {1: [5, 4], 2: [3, 2], 3: [1], 4: []}
    assert list(paginate(lambda n: pages[n], key=int)) == [5, 4, 3, 2, 1]
    assert list(paginate(lambda n: pages[n], key=int, stop_when=lambda x: x <= 3)) == [5, 4]


def test_paginate_stops_when_last_page_repeats() -> None:
    pages = {1: [2, 1], 2: [0]}
    assert list(paginate(lambda n: pages.get(n, [0]), key=int)) == [2, 1, 0]


def test_revisions_all_and_incremental() -> None:
    api = make_api({"history/PageRevisionListModule": revision_module(5)})
    assert [r.revision for r in api.revisions(1)] == [4, 3, 2, 1, 0]
    assert [r.revision for r in api.revisions(1, newer_than=2)] == [4, 3]
    assert api.revisions(1)[0].global_revision == 1004


def test_file_ids_stop_when_nothing_new() -> None:
    def files(form: dict[str, str]) -> dict[str, Any]:
        rows = {"1": '<tr id="file-row-1"/><tr id="file-row-2"/>', "2": '<tr id="file-row-3"/>'}
        # Wikidot repeats the last page for out-of-range page numbers.
        return {"status": "ok", "body": f"<table>{rows.get(form['page'], rows['2'])}</table>"}

    api = make_api({"files/PageFilesModule": files})
    assert api.file_ids(1) == [1, 2, 3]


def test_lock_detection() -> None:
    api = make_api(
        {
            "edit/PageEditModule": lambda f: {"status": "no_permission", "message": "locked"},
            "forum/sub/ForumNewPostFormModule": lambda f: {
                "status": "no_permission",
                "message": '<a href="/x">log in</a>',
            },
        }
    )
    assert api.is_page_locked(1) is True
    assert api.is_thread_locked(1) is False


def test_post_revision_error_raises() -> None:
    api = make_api(
        {"forum/sub/ForumPostRevisionModule": lambda f: {"status": "ok", "body": "nope"}}
    )
    with pytest.raises(WikidashError):
        api.post_revision(1)


def test_post_revision_ok() -> None:
    api = make_api(
        {
            "forum/sub/ForumPostRevisionModule": lambda f: {
                "status": "ok",
                "body": "ok",
                "title": "T",
                "content": "<p>c</p>",
            }
        }
    )
    body = api.post_revision(1)
    assert (body.title, body.content) == ("T", "<p>c</p>")


def test_page_info_requests_noredirect_url() -> None:
    html = "<html><head><script>WIKIREQUEST.info.pageId = 9;</script></head></html>"
    api = make_api({}, pages={"/some:page/noredirect/true": html})
    assert api.page_info("some:page").page_id == 9
