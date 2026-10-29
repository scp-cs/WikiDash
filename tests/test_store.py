import json
from pathlib import Path

from wikidash.store import PersistentDict, PersistentSet, write_json


def test_write_json_is_indented_and_atomic(tmp_path: Path) -> None:
    target = tmp_path / "meta" / "x.json"
    write_json(target, {"a": 1})
    assert target.read_text(encoding="utf-8") == '{\n    "a": 1\n}'
    assert [p.name for p in target.parent.iterdir()] == ["x.json"]


def test_persistent_dict_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    data = PersistentDict(path)
    data["1"] = "page"
    data.save()
    assert json.loads(path.read_text()) == {"1": "page"}
    assert PersistentDict(path).get("1") == "page"


def test_persistent_dict_skips_clean_save(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    PersistentDict(path).save()
    assert not path.exists()


def test_persistent_set(tmp_path: Path) -> None:
    path = tmp_path / "s.json"
    items = PersistentSet(path)
    items.add(1)
    items.add(1)
    items.add(2)
    items.discard(1)
    items.save()
    assert json.loads(path.read_text()) == [2]
