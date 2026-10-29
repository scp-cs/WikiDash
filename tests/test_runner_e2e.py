"""A whole run against a fake wikidot.com served from memory (no network)."""

import json
from pathlib import Path
from urllib.parse import parse_qs

import httpx

from wikidash.config import Config
from wikidash.http import HttpClient
from wikidash.progress import StatusSink
from wikidash.runner import WikiRunner, run_all
from wikidash.userlist import UserList

WIKI = "https://t.wikidot.com"
USER = (
    '<span class="printuser"><a href="http://www.wikidot.com/user:info/bob" '
    'onclick="WIKIDOT.page.listeners.userInfo(7); return false;">Bob</a></span>'
)
PROFILE = """<div class="col-md-9"><h1 class="profile-title">Bob</h1>
<dl class="dl-horizontal"><dt>Wikidot User since:</dt><dd>6 Sep 2022, 16:33</dd></dl>
<a onclick="WIKIDOT.modules.UserInfoModule.listeners.addContact(event,7)">x</a></div>"""

SITEMAP = """<urlset>
<url><loc>https://t.wikidot.com/scp-001</loc><lastmod>2024-01-02T03:04:05+00:00</lastmod></url>
<url><loc>https://t.wikidot.com/</loc></url>
</urlset>"""
PAGE = "<html><head><script>WIKIREQUEST.info.pageId = 10;</script></head></html>"
REVISIONS = (
    "<table><tr><th>h</th></tr>"
    f'<tr><td>0.</td><td></td><td>N</td><td><a onclick="v(900)">v</a></td><td>{USER}</td>'
    '<td><span class="odate time_5">d</span></td><td>created</td></tr></table>'
)


class FakeSite:
    def __init__(self) -> None:
        self.requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.requests.append(f"{request.method} {request.url.host}{path}")
        if request.url.host == "www.wikidot.com":
            return httpx.Response(200, text=PROFILE)
        if request.method == "POST":
            return httpx.Response(200, json=self._module(request))
        if path == "/sitemap.xml":
            return httpx.Response(200, text=SITEMAP)
        if path == "/system:recent-changes":
            return httpx.Response(200, headers={"Set-Cookie": "wikidot_token7=t; Path=/"})
        if path == "/forum/start/hidden/show":
            return httpx.Response(200, text="<html><body></body></html>")
        return httpx.Response(200, text=PAGE)

    @staticmethod
    def _module(request: httpx.Request) -> dict[str, object]:
        form = parse_qs(request.content.decode())
        module = form["moduleName"][0]
        bodies = {
            "history/PageRevisionListModule": REVISIONS if form.get("page") == ["1"] else "",
            "history/PageSourceModule": '<div class="page-source">hello</div>',
            "pagerate/WhoRatedPageModule": f"<div>{USER}<span>+</span><br/></div>",
            "files/PageFilesModule": "<table></table>",
        }
        if module == "edit/PageEditModule":
            return {"status": "ok", "message": '<a href="/x">edit</a>'}
        return {"status": "ok", "body": bodies[module]}


def make_runner(tmp_path: Path, site: FakeSite) -> tuple[WikiRunner, UserList, Config]:
    config = Config.from_dict(
        {"base_directory": str(tmp_path), "wikis": [{"name": "t", "url": WIKI + "/"}]}
    )
    client = HttpClient(transport=httpx.MockTransport(site))
    users = UserList(tmp_path / "_users", client, cache_seconds=3600)
    return WikiRunner(config.wikis[0], config, client, users, StatusSink()), users, config


def test_full_run_then_noop_second_run(tmp_path: Path) -> None:
    site = FakeSite()
    runner, users, _ = make_runner(tmp_path, site)
    runner.run()
    users.fetch_pending()

    root = tmp_path / "t"
    meta = json.loads((root / "meta" / "pages" / "scp-001.json").read_text("utf-8"))
    assert meta["page_id"] == 10 and meta["votings"] == [[7, True]]
    assert meta["revisions"][0]["global_revision"] == 900
    assert (root / "pages" / "scp-001.7z").is_file()
    assert json.loads((root / "meta" / "sitemap.json").read_text()) == {"scp-001": 1704164645000}
    assert json.loads((root / "meta" / "page_id_map.json").read_text()) == {"10": "scp-001"}
    assert json.loads((tmp_path / "_users" / "0.json").read_text())["7"]["username"] == "bob"

    # Second run: the page is unchanged, so nothing but the sitemap is fetched.
    site.requests.clear()
    second, _, _ = make_runner(tmp_path, site)
    second.run()
    fetched = [r for r in site.requests if "scp-001" in r or "ajax-module-connector" in r]
    assert fetched == []


def test_run_all_reports_failures(tmp_path: Path) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    config = Config.from_dict(
        {"base_directory": str(tmp_path), "wikis": [{"name": "t", "url": WIKI}]}
    )
    client = HttpClient(transport=httpx.MockTransport(broken))
    users = UserList(tmp_path / "_users", client, cache_seconds=1)

    failed = run_all(
        config, lambda wiki: WikiRunner(wiki, config, client, users, StatusSink())
    )
    assert failed == ["t"]
