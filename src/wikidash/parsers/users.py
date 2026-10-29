"""Extracting user references from Wikidot's user spans."""

import re
from collections.abc import Callable
from dataclasses import dataclass

from bs4 import Tag

from .html import attr

_USER_ID_FROM_ONCLICK = re.compile(r"WIKIDOT\.page\.listeners\.userInfo\((\d+)\);")
_USERNAME_FROM_HREF = re.compile(r"user:info/(.*)")

# Called for every user (id, username) seen while parsing, so the caller can
# queue a profile fetch. Parsers themselves never touch the network.
UserSink = Callable[[int, str], None]


def ignore_users(user_id: int, username: str) -> None:
    """Default sink."""


@dataclass(frozen=True)
class UserRef:
    user_id: int
    username: str | None  # unknown for deleted users


def extract_user(elem: Tag | None) -> UserRef | None:
    """Return the user in `elem`, or None for anonymous/unknown authors."""
    if elem is None:
        return None

    link = elem.find("a")
    link = link if isinstance(link, Tag) else None
    onclick = _USER_ID_FROM_ONCLICK.search(attr(link, "onclick") or "")
    href = _USERNAME_FROM_HREF.search(attr(link, "href") or "")
    username = href.group(1) if href else None

    if onclick:
        return UserRef(int(onclick.group(1)), username)

    # Deleted users have no link, only their id.
    deleted = elem.select_one("span.deleted")
    raw_id = attr(deleted, "data-id") or attr(elem, "data-id")
    if raw_id is not None and raw_id.isdigit():
        return UserRef(int(raw_id), username)
    return None


def user_id_of(elem: Tag | None, on_user: UserSink = ignore_users) -> int | None:
    """User id in `elem`; reports (id, username) to `on_user` when both are known."""
    user = extract_user(elem)
    if user is None:
        return None
    if user.username is not None:
        on_user(user.user_id, user.username)
    return user.user_id
