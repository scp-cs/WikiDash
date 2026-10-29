"""Forum shapes: what wikidot shows (`*Info`) and what is stored on disk (`*Meta`).

Stored JSON matches the original archive: `last`/`lastEdit` style fields are
left out when unknown.
"""

from dataclasses import dataclass, field
from typing import Any

from .models import UserId

FORUM_CATEGORY_METADATA_VERSION = 1
FORUM_THREAD_METADATA_VERSION = 1


# --- as shown by wikidot -------------------------------------------------


@dataclass
class CategoryInfo:
    id: int
    title: str
    description: str
    threads: int
    posts: int
    last: int | None  # unix seconds of the newest post
    last_user: UserId


@dataclass
class ThreadInfo:
    id: int
    title: str
    description: str
    posts_num: int
    sticky: bool
    started: int
    started_user: UserId
    last: int | None  # None for threads without posts
    last_user: UserId


@dataclass
class PostRevision:
    id: int
    author: UserId
    stamp: int


@dataclass
class RevisionBody:
    title: str
    content: str  # HTML


@dataclass
class PostInfo:
    id: int
    title: str
    poster: UserId
    content: str  # HTML of the newest revision
    stamp: int
    last_edit: int | None = None
    last_edit_by: UserId = None
    children: list["PostInfo"] = field(default_factory=list)


# --- as stored on disk ---------------------------------------------------


@dataclass
class StoredPostRevision:
    title: str
    author: UserId
    id: int
    stamp: int

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "author": self.author, "id": self.id, "stamp": self.stamp}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StoredPostRevision":
        return cls(raw["title"], raw["author"], raw["id"], raw["stamp"])


@dataclass
class StoredPost:
    """A post without its content (the HTML lives in the thread's files)."""

    id: int
    title: str
    poster: UserId
    stamp: int
    last_edit: int | None = None
    last_edit_by: UserId = None
    revisions: list[StoredPostRevision] = field(default_factory=list)
    children: list["StoredPost"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "poster": self.poster,
            "stamp": self.stamp,
        }
        if self.last_edit is not None:
            data["lastEdit"] = self.last_edit
            data["lastEditBy"] = self.last_edit_by
        data["revisions"] = [r.to_dict() for r in self.revisions]
        data["children"] = [c.to_dict() for c in self.children]
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StoredPost":
        return cls(
            id=raw["id"],
            title=raw["title"],
            poster=raw["poster"],
            stamp=raw["stamp"],
            last_edit=raw.get("lastEdit"),
            last_edit_by=raw.get("lastEditBy"),
            revisions=[StoredPostRevision.from_dict(r) for r in raw.get("revisions", [])],
            children=[cls.from_dict(c) for c in raw.get("children", [])],
        )

    def walk(self) -> "list[StoredPost]":
        """This post followed by all its descendants, depth first."""
        found = [self]
        for child in self.children:
            found.extend(child.walk())
        return found


@dataclass
class CategoryMeta:
    id: int
    title: str
    description: str
    threads: int
    posts: int
    last: int | None = None
    last_user: UserId = None
    full_scan: bool = False  # every thread of the category was fetched at least once
    last_page: int = 0  # resume point of an interrupted scan
    version: int = FORUM_CATEGORY_METADATA_VERSION

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "id": self.id,
        }
        if self.last is not None:
            data["last"] = self.last
        data.update(
            {
                "posts": self.posts,
                "threads": self.threads,
                "lastUser": self.last_user,
                "full_scan": self.full_scan,
                "last_page": self.last_page,
                "version": self.version,
            }
        )
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "CategoryMeta":
        return cls(
            id=raw["id"],
            title=raw["title"],
            description=raw["description"],
            threads=raw["threads"],
            posts=raw["posts"],
            last=raw.get("last"),
            last_user=raw.get("lastUser"),
            full_scan=raw.get("full_scan", False),
            last_page=raw.get("last_page", 0),
            version=raw.get("version", 0),
        )


@dataclass
class ThreadMeta:
    id: int
    title: str
    description: str
    posts_num: int
    sticky: bool
    started: int
    started_user: UserId
    last: int | None = None
    last_user: UserId = None
    is_locked: bool = False
    version: int = FORUM_THREAD_METADATA_VERSION
    posts: list[StoredPost] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"title": self.title, "id": self.id, "description": self.description}
        if self.last is not None:
            data["last"] = self.last
            data["lastUser"] = self.last_user
        data.update(
            {
                "started": self.started,
                "startedUser": self.started_user,
                "postsNum": self.posts_num,
                "sticky": self.sticky,
                "isLocked": self.is_locked,
                "version": self.version,
                "posts": [p.to_dict() for p in self.posts],
            }
        )
        return data

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ThreadMeta":
        return cls(
            id=raw["id"],
            title=raw["title"],
            description=raw["description"],
            posts_num=raw["postsNum"],
            sticky=raw["sticky"],
            started=raw["started"],
            started_user=raw["startedUser"],
            last=raw.get("last"),
            last_user=raw.get("lastUser"),
            is_locked=raw.get("isLocked", False),
            version=raw.get("version", 0),
            posts=[StoredPost.from_dict(p) for p in raw.get("posts", [])],
        )

    def all_posts(self) -> list[StoredPost]:
        return [post for top in self.posts for post in top.walk()]
