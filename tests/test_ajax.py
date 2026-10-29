import json
from urllib.parse import parse_qs

import httpx
import pytest

from wikidash.ajax import WikidotAjax
from wikidash.errors import WikidotError
from wikidash.http import HttpClient

WIKI = "https://test.wikidot.com"


class FakeWikidot:
    """Hands out tokens and rejects the first ajax call with wrong_token7."""

    def __init__(self, reject_first: bool = False) -> None:
        self.reject_first = reject_first
        self.token_counter = 0
        self.seen_tokens: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system:recent-changes":
            self.token_counter += 1
            cookie = f"wikidot_token7=tok{self.token_counter}; Path=/"
            return httpx.Response(200, headers={"Set-Cookie": cookie})
        form = parse_qs(request.content.decode())
        self.seen_tokens.append(form["wikidot_token7"][0])
        assert form["moduleName"] == ["some/Module"]
        if self.reject_first and len(self.seen_tokens) == 1:
            return httpx.Response(200, json={"status": "wrong_token7"})
        return httpx.Response(200, json={"status": "ok", "body": "<p>hi</p>"})


def make_ajax(fake: FakeWikidot, slept: list[float]) -> WikidotAjax:
    client = HttpClient(transport=httpx.MockTransport(fake))
    return WikidotAjax(client, WIKI, cooldown=30, sleep=slept.append)


def test_call_fetches_token_once() -> None:
    fake = FakeWikidot()
    ajax = make_ajax(fake, [])
    assert ajax.call("some/Module", page_id=1)["body"] == "<p>hi</p>"
    ajax.call("some/Module", page_id=2)
    assert fake.seen_tokens == ["tok1", "tok1"]


def test_wrong_token_waits_refreshes_and_retries() -> None:
    fake = FakeWikidot(reject_first=True)
    slept: list[float] = []
    ajax = make_ajax(fake, slept)
    assert ajax.call("some/Module")["status"] == "ok"
    assert slept == [30]
    assert fake.seen_tokens == ["tok1", "tok2"]


def test_error_status_raises_unless_allowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system:recent-changes":
            return httpx.Response(200, headers={"Set-Cookie": "wikidot_token7=t; Path=/"})
        return httpx.Response(200, content=json.dumps({"status": "no_permission", "message": "x"}))

    ajax = WikidotAjax(HttpClient(transport=httpx.MockTransport(handler)), WIKI)
    with pytest.raises(WikidotError):
        ajax.call("some/Module")
    assert ajax.call("some/Module", allow_errors=True)["status"] == "no_permission"
