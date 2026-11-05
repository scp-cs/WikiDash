"""JSON persistence: atomic writes and small persistent collections."""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

JSON_INDENT = 4  # matches the original archive format


def read_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, data: Any) -> None:
    """Write JSON atomically so a crash never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=JSON_INDENT, ensure_ascii=False)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class PersistentDict:
    """A dict backed by one JSON file; `save()` writes only when changed.

    Keys are stored as strings on disk (JSON), so they are always strings here.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._dirty = False
        self._data: dict[str, Any] = read_json(path) if path.exists() else {}

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __len__(self) -> int:
        return len(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def items(self) -> list[tuple[str, Any]]:
        with self._lock:
            return list(self._data.items())

    def __setitem__(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._dirty = True

    def pop(self, key: str) -> None:
        with self._lock:
            if key in self._data:
                del self._data[key]
                self._dirty = True

    def save(self) -> None:
        with self._lock:
            if self._dirty:
                write_json(self._path, self._data)
                self._dirty = False


class PersistentSet:
    """A set backed by a JSON list (the on-disk format of the original)."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._dirty = False
        self._items: list[Any] = read_json(path) if path.exists() else []

    def __contains__(self, item: Any) -> bool:
        return item in self._items

    def __len__(self) -> int:
        return len(self._items)

    def to_list(self) -> list[Any]:
        with self._lock:
            return list(self._items)

    def add(self, item: Any) -> None:
        with self._lock:
            if item not in self._items:
                self._items.append(item)
                self._dirty = True

    def discard(self, item: Any) -> None:
        with self._lock:
            if item in self._items:
                self._items.remove(item)
                self._dirty = True

    def save(self) -> None:
        with self._lock:
            if self._dirty:
                write_json(self._path, self._items)
                self._dirty = False
