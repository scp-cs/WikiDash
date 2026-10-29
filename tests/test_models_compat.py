"""Real files from the original archive must survive load -> model -> dump unchanged."""

import json
from pathlib import Path

import pytest

from wikidash.forum_models import CategoryMeta, ThreadMeta
from wikidash.models import PageMeta

FIXTURES = Path(__file__).parent / "fixtures"


def _load(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as file:
        data: dict[str, object] = json.load(file)
    return data


@pytest.mark.parametrize("path", sorted((FIXTURES / "meta_pages").glob("*.json")), ids=lambda p: p.name)
def test_page_meta_roundtrip(path: Path) -> None:
    raw = _load(path)
    assert PageMeta.from_dict(raw).to_dict() == raw  # type: ignore[arg-type]


@pytest.mark.parametrize("path", sorted((FIXTURES / "meta_forum").glob("*.json")), ids=lambda p: p.name)
def test_thread_meta_roundtrip(path: Path) -> None:
    raw = _load(path)
    thread = ThreadMeta.from_dict(raw)  # type: ignore[arg-type]
    assert thread.to_dict() == raw
    assert len(thread.all_posts()) >= 2


@pytest.mark.parametrize(
    "path", sorted((FIXTURES / "meta_forum_category").glob("*.json")), ids=lambda p: p.name
)
def test_category_meta_roundtrip(path: Path) -> None:
    raw = _load(path)
    dumped = CategoryMeta.from_dict(raw).to_dict()  # type: ignore[arg-type]
    assert dumped == raw
    assert list(dumped) == list(raw)


def test_page_meta_key_order_matches_original() -> None:
    raw = _load(FIXTURES / "meta_pages" / "026-exploration-logs.json")
    dumped = PageMeta.from_dict(raw).to_dict()  # type: ignore[arg-type]
    assert list(dumped) == list(raw)
