import json
import shutil
from pathlib import Path

from wikidash.models import PageMeta
from wikidash.workspace import Workspace

FIXTURES = Path(__file__).parent / "fixtures"


def test_page_meta_roundtrip_uses_normalized_name(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    raw = json.loads((FIXTURES / "meta_pages" / "about-the-scp-foundation.json").read_text("utf-8"))
    ws.write_page_meta("component:thing", PageMeta.from_dict(raw))
    assert (tmp_path / "meta" / "pages" / "component_thing.json").is_file()
    assert ws.page_meta_exists("component:thing")
    assert ws.read_page_meta("component:thing") == PageMeta.from_dict(raw)
    assert ws.read_page_meta("missing") is None


def test_revisions_loose_then_compressed(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    ws.write_revision("a:b", 0, "zero")
    ws.write_revision("a:b", 1, "jedna ě")
    assert ws.local_revisions("a:b") == {0, 1}

    ws.compress_revisions("a:b")
    assert not (tmp_path / "pages" / "a_b").exists()
    assert ws.revision_archive("a:b").read("1.txt").decode() == "jedna ě"
    assert ws.local_revisions("a:b") == {0, 1}

    ws.write_revision("a:b", 2, "dva")
    assert ws.local_revisions("a:b") == {0, 1, 2}
    ws.compress_revisions("a:b")
    assert sorted(ws.revision_archive("a:b").names()) == ["0.txt", "1.txt", "2.txt"]


def test_reads_revisions_of_original_archive(tmp_path: Path) -> None:
    (tmp_path / "pages").mkdir()
    shutil.copy(FIXTURES / "component_admin-list.7z", tmp_path / "pages" / "component_admin-list.7z")
    assert Workspace(tmp_path).local_revisions("component:admin-list") == {0}


def test_remove_page_deletes_everything(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    raw = json.loads((FIXTURES / "meta_pages" / "about-the-scp-foundation.json").read_text("utf-8"))
    ws.write_page_meta("x:y", PageMeta.from_dict(raw))
    ws.write_revision("x:y", 0, "t")
    ws.compress_revisions("x:y")
    ws.write_revision("x:y", 1, "t")
    file = ws.file_path("x%3Ay", 5)
    file.parent.mkdir(parents=True)
    file.write_bytes(b"data")

    ws.remove_page("x:y")
    assert not ws.page_meta_exists("x:y")
    assert ws.local_revisions("x:y") == set()
    assert not file.parent.exists()


def test_persistent_collections_save(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    ws.pending_revisions["123"] = 9
    ws.pending_pages.add("some-page")
    ws.save()
    assert json.loads((tmp_path / "meta" / "pending_revisions.json").read_text()) == {"123": 9}
    assert json.loads((tmp_path / "meta" / "pending_pages.json").read_text()) == ["some-page"]
    assert Workspace(tmp_path).pending_revisions.get("123") == 9
