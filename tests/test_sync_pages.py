from pathlib import Path

from fakes import FakePage, FakeWikidot
from wikidash.progress import Counters
from wikidash.sync_files import FileSyncer
from wikidash.sync_pages import PageSyncer
from wikidash.workspace import Workspace


def make(tmp_path: Path) -> tuple[Workspace, FakeWikidot, PageSyncer, Counters]:
    workspace = Workspace(tmp_path)
    wikidot = FakeWikidot()
    counters = Counters()
    syncer = PageSyncer(workspace, wikidot, FileSyncer(workspace, wikidot), counters)
    return workspace, wikidot, syncer, counters


def test_new_page_is_fully_archived(tmp_path: Path) -> None:
    ws, wikidot, syncer, counters = make(tmp_path)
    wikidot.add_page("scp:001", FakePage(10, revisions=3, files={7: b"hello"}))

    syncer.sync_page("scp:001", 1000, previous=None)

    meta = ws.read_page_meta("scp:001")
    assert meta is not None
    assert (meta.page_id, meta.title, meta.tags, meta.sitemap_update) == (10, "Title", ["tag"], 1000)
    assert [r.revision for r in meta.revisions] == [2, 1, 0]  # newest first
    assert meta.votings == [(1, True)] and meta.is_locked is False
    assert [f.file_id for f in meta.files] == [7]
    assert ws.local_revisions("scp:001") == {0, 1, 2}
    assert ws.revision_archive("scp:001").read("2.txt") == b"source 1002"
    assert ws.file_path("some%3Apage", 7).read_bytes() == b"hello"
    assert ws.page_id_map.get("10") == "scp:001"
    assert (counters.done, counters.postponed) == (1, 0)


def test_unchanged_page_is_skipped(tmp_path: Path) -> None:
    _ws, wikidot, syncer, counters = make(tmp_path)
    wikidot.add_page("a", FakePage(1))
    syncer.sync_page("a", 500, previous=None)
    wikidot.calls.clear()

    syncer.sync_page("a", 500, previous={"a": 500})
    assert wikidot.calls == []
    assert counters.done == 2


def test_updated_page_fetches_only_new_revisions(tmp_path: Path) -> None:
    ws, wikidot, syncer, _ = make(tmp_path)
    page = FakePage(1, revisions=2)
    wikidot.add_page("a", page)
    syncer.sync_page("a", 500, previous=None)
    wikidot.calls.clear()

    page.revision_count = 4
    syncer.sync_page("a", 600, previous={"a": 500})

    meta = ws.read_page_meta("a")
    assert meta is not None and [r.revision for r in meta.revisions] == [3, 2, 1, 0]
    assert "revisions:1:1" in wikidot.calls  # asked only for revisions above 1
    assert sorted(c for c in wikidot.calls if c.startswith("source:")) == ["source:102", "source:103"]


def test_failed_revision_is_postponed_then_picked_up(tmp_path: Path) -> None:
    ws, wikidot, syncer, counters = make(tmp_path)
    wikidot.add_page("a", FakePage(1, revisions=2))
    wikidot.failing_revisions = {101}

    syncer.sync_page("a", 500, previous=None)
    assert ws.local_revisions("a") == {0}
    assert ws.pending_revisions.get("101") == 1
    assert counters.postponed == 1

    wikidot.failing_revisions = set()
    syncer.sync_page("a", 500, previous=None)  # page unchanged, but no previous sitemap
    assert ws.local_revisions("a") == {0, 1}
    assert ws.pending_revisions.get("101") is None


def test_recreated_page_discards_old_data(tmp_path: Path) -> None:
    ws, wikidot, syncer, _ = make(tmp_path)
    wikidot.add_page("a", FakePage(1, revisions=3))
    syncer.sync_page("a", 500, previous=None)

    wikidot.add_page("a", FakePage(99, revisions=1))  # deleted and created again
    syncer.sync_page("a", 600, previous={"a": 500})

    meta = ws.read_page_meta("a")
    assert meta is not None and meta.page_id == 99 and len(meta.revisions) == 1
    assert ws.local_revisions("a") == {0}
    assert ws.page_id_map.get("1") is None and ws.page_id_map.get("99") == "a"


def test_unreachable_page_is_postponed(tmp_path: Path) -> None:
    ws, wikidot, syncer, counters = make(tmp_path)
    wikidot.add_page("a", FakePage(1))
    wikidot.unreachable_pages = {"a"}

    syncer.sync_page("a", 1, previous=None)

    assert ws.pending_pages.to_list() == ["a"]
    assert not ws.page_meta_exists("a")
    assert (counters.done, counters.postponed) == (0, 1)

    wikidot.unreachable_pages = set()
    syncer.sync_page("a", 1, previous=None)
    assert ws.pending_pages.to_list() == [] and counters.done == 1


def test_removed_file_is_deleted(tmp_path: Path) -> None:
    ws, wikidot, syncer, _ = make(tmp_path)
    page = FakePage(1, files={7: b"x", 8: b"y"})
    wikidot.add_page("a", page)
    syncer.sync_page("a", 1, previous=None)
    assert ws.file_path("some%3Apage", 8).exists()

    del page.files[8]
    syncer.sync_page("a", 2, previous={"a": 1})
    assert not ws.file_path("some%3Apage", 8).exists()
    assert ws.file_path("some%3Apage", 7).exists()
