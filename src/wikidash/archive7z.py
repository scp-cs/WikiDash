"""Small API over .7z files: list, read and add members.

The original archiver kept one archive per page (`pages/<name>.7z`, members
`<rev>.txt`) and one per forum thread. Archives are small, so adding members
rewrites the file atomically instead of appending in place.
"""

import os
from collections.abc import Mapping
from pathlib import Path

import py7zr
from py7zr.io import BytesIOFactory

_MAX_MEMBER_BYTES = 1 << 30  # py7zr refuses to buffer more than this per archive


class Archive7z:
    def __init__(self, path: Path) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def names(self) -> list[str]:
        """Names of all file members (directories excluded)."""
        if not self.exists():
            return []
        with py7zr.SevenZipFile(self.path, "r") as archive:
            return [info.filename for info in archive.list() if not info.is_directory]

    def read_all(self) -> dict[str, bytes]:
        if not self.exists():
            return {}
        factory = BytesIOFactory(_MAX_MEMBER_BYTES)
        with py7zr.SevenZipFile(self.path, "r") as archive:
            archive.extract(targets=None, factory=factory)
        members: dict[str, bytes] = {}
        for name, buffer in factory.products.items():
            buffer.seek(0)
            members[name] = buffer.read()
        return members

    def read(self, name: str) -> bytes:
        members = self.read_all()
        if name not in members:
            raise KeyError(f"{name} is not in {self.path}")
        return members[name]

    def add(self, members: Mapping[str, bytes]) -> None:
        """Add (or replace) members, keeping the existing ones."""
        combined = {**self.read_all(), **members}
        self._write(combined)

    def _write(self, members: Mapping[str, bytes]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        try:
            with py7zr.SevenZipFile(tmp, "w") as archive:
                for name, data in sorted(members.items()):
                    archive.writestr(data, name)
            os.replace(tmp, self.path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
