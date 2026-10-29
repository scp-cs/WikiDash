import json
from pathlib import Path

import httpx

from fakes import FakePage, FakeWikidot
from wikidash.progress import Counters, ErrorKind, Status
from wikidash.scuttle import ScuttleConnector
from wikidash.sync_files import FileSyncer
from wikidash.sync_pages import PageSyncer
from wikidash.sync_pending import retry_pending_revisions
from wikidash.workspace import Workspace


def test_scuttle_messages_are_double_encoded() -> None:
    bodies: list[bytes] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/backup/status"
        bodies.append(request.content)
        return httpx.Response(200)

    scuttle = ScuttleConnector("scp-cs", "http://scuttle", transport=httpx.MockTransport(handler))
    scuttle.handshake()
    scuttle.preflight(42)
    scuttle.progress(Status.PAGES_MAIN, done=3, postponed=0)
    scuttle.error(ErrorKind.VOTE_FETCH, "some-page", "boom")

    decoded = [json.loads(json.loads(body)) for body in bodies]
    assert decoded[0] == {"tag": "scp-cs", "type": 0}
    assert decoded[1] == {"tag": "scp-cs", "type": 1, "total": 42}
    assert decoded[2] == {"tag": "scp-cs", "type": 2, "status": 1, "done": 3, "postponed": 0}
    assert decoded[3] == {
        "tag": "scp-cs", "type": 4, "errorKind": 2, "name": "some-page", "errorStr": "boom"
    }
    assert bodies[0] == b'"{\\"tag\\": \\"scp-cs\\", \\"type\\": 0}"'


def test_scuttle_outage_is_ignored() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    ScuttleConnector("x", "http://scuttle", transport=httpx.MockTransport(handler)).finish()


def test_pending_revisions_are_retried(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    wikidot = FakeWikidot()
    wikidot.add_page("a", FakePage(1, revisions=2))
    wikidot.add_page("nav:side", FakePage(2, revisions=1))
    wikidot.failing_revisions = {101, 200}
    syncer = PageSyncer(ws, wikidot, FileSyncer(ws, wikidot), Counters())
    syncer.sync_page("a", 1, None)
    syncer.sync_page("nav:side", 1, None)
    assert set(ws.pending_revisions.items()) == {("101", 1), ("200", 2)}

    retry_pending_revisions(ws, wikidot)  # still failing: "a" stays, "nav:" is given up
    assert dict(ws.pending_revisions.items()) == {"101": 1}

    wikidot.failing_revisions = set()
    retry_pending_revisions(ws, wikidot)
    assert dict(ws.pending_revisions.items()) == {}
    assert ws.local_revisions("a") == {0, 1}


def test_unknown_pending_revision_is_dropped(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    ws.pending_revisions["555"] = 999
    retry_pending_revisions(ws, FakeWikidot())
    assert len(ws.pending_revisions) == 0
