"""Data shapes shared by parsers, API and storage.

`to_dict` output matches the JSON written by the original WikiComma: fields
that were `undefined` there are simply left out.
"""

from dataclasses import asdict, dataclass, field
from typing import Any

# Wikidot user ids; None means anonymous or unknown.
UserId = int | None


@dataclass
class PageRevision:
    revision: int  # per-page counter
    global_revision: int  # wikidot-wide id, used to fetch the source
    author: UserId
    stamp: int | None = None  # unix seconds
    flags: str = ""
    commentary: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "revision": self.revision,
            "global_revision": self.global_revision,
            "author": self.author,
        }
        if self.stamp is not None:
            data["stamp"] = self.stamp
        data["flags"] = self.flags
        data["commentary"] = self.commentary
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PageRevision":
        return cls(
            revision=raw["revision"],
            global_revision=raw["global_revision"],
            author=raw.get("author"),
            stamp=raw.get("stamp"),
            flags=raw.get("flags", ""),
            commentary=raw.get("commentary", ""),
        )


FILE_METADATA_VERSION = 1
PAGE_METADATA_VERSION = 18


@dataclass
class FileMeta:
    file_id: int
    name: str
    url: str
    size: str  # as shown by wikidot, e.g. "45.47 kB (46561 Bytes)"
    size_bytes: int | None
    mime: str
    content: str  # `file`-style description of the content
    author: UserId
    stamp: int | None  # unix seconds
    internal_version: int = FILE_METADATA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "FileMeta":
        return cls(**raw)


@dataclass
class PageMeta:
    name: str
    page_id: int
    version: int = PAGE_METADATA_VERSION
    revisions: list[PageRevision] = field(default_factory=list)  # newest first
    files: list[FileMeta] = field(default_factory=list)
    parent: str | None = None
    rating: int | None = None
    forum_thread: int | None = None
    tags: list[str] | None = None
    title: str | None = None
    sitemap_update: int | None = None  # epoch milliseconds
    votings: list[tuple[UserId, bool]] | None = None
    is_locked: bool | None = None

    def to_dict(self) -> dict[str, Any]:
        """JSON in the original key order; unset (None) optional fields are left out."""
        data: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "revisions": [r.to_dict() for r in self.revisions],
            "files": [f.to_dict() for f in self.files],
            "page_id": self.page_id,
        }
        optional: dict[str, Any] = {
            "parent": self.parent,
            "rating": self.rating,
            "forum_thread": self.forum_thread,
            "tags": self.tags,
            "title": self.title,
            "sitemap_update": self.sitemap_update,
            "votings": None if self.votings is None else [list(v) for v in self.votings],
            "is_locked": self.is_locked,
        }
        data.update({key: value for key, value in optional.items() if value is not None})
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PageMeta":
        votings = raw.get("votings")
        return cls(
            name=raw["name"],
            page_id=raw["page_id"],
            version=raw.get("version", 0),
            revisions=[PageRevision.from_dict(r) for r in raw.get("revisions", [])],
            files=[FileMeta.from_dict(f) for f in raw.get("files", [])],
            parent=raw.get("parent"),
            rating=raw.get("rating"),
            forum_thread=raw.get("forum_thread"),
            tags=raw.get("tags"),
            title=raw.get("title"),
            sitemap_update=raw.get("sitemap_update"),
            votings=None if votings is None else [(v[0], v[1]) for v in votings],
            is_locked=raw.get("is_locked"),
        )


@dataclass
class PageInfo:
    """What can be scraped from a rendered page (not from ajax modules)."""

    page_id: int | None = None
    title: str | None = None
    rating: int | None = None
    forum_thread: int | None = None
    tags: list[str] = field(default_factory=list)
    parent: str | None = None
