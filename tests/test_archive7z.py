import shutil
from pathlib import Path

from wikidash.archive7z import Archive7z

FIXTURE = Path(__file__).parent / "fixtures" / "component_admin-list.7z"


def test_reads_archive_written_by_original_wikicomma() -> None:
    archive = Archive7z(FIXTURE)
    assert archive.names() == ["0.txt"]
    assert archive.read("0.txt").startswith(b"\n{$str_admins}")


def test_missing_archive_is_empty(tmp_path: Path) -> None:
    archive = Archive7z(tmp_path / "nope.7z")
    assert archive.names() == []
    assert archive.read_all() == {}


def test_add_keeps_existing_members(tmp_path: Path) -> None:
    path = tmp_path / "pages" / "x.7z"
    shutil.copy(FIXTURE, tmp_path / "orig.7z")
    archive = Archive7z(path)
    archive.add({"1.txt": b"one"})
    archive.add({"2.txt": "dva ě".encode(), "1.txt": b"uno"})
    assert archive.names() == ["1.txt", "2.txt"]
    assert archive.read("1.txt") == b"uno"
    assert archive.read("2.txt").decode() == "dva ě"
    assert [p.name for p in path.parent.iterdir()] == ["x.7z"]
