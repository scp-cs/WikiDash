"""Who rated a page (pagerate/WhoRatedPageModule)."""

from bs4 import Tag

from wikidash.errors import ParseError
from wikidash.models import UserId

from .html import child_tags, parse_fragment
from .users import UserSink, ignore_users, user_id_of


def parse_voters(body: str, on_user: UserSink = ignore_users) -> list[tuple[UserId, bool]] | None:
    """List of (user, is_upvote), or None when the module has no vote list.

    The list is a flat run of `<span>user</span><span>+</span><br>` triples.
    """
    container = next((t for t in child_tags(parse_fragment(body)) if t.name == "div"), None)
    if container is None:
        return None

    votes: list[tuple[UserId, bool]] = []
    user: UserId | None = None
    have_user = False
    upvote: bool | None = None

    for position, tag in enumerate(child_tags(container)):
        if tag.name == "span" and not have_user:
            user = user_id_of(tag, on_user)
            have_user = True
        elif tag.name == "span" and upvote is None:
            upvote = _parse_vote(tag, position)
        elif tag.name == "br" and have_user and upvote is not None:
            votes.append((user, upvote))
            have_user, upvote = False, None
        elif tag.name in ("span", "br"):
            raise ParseError(f"Malformed voting list near element {position}")
    return votes


def _parse_vote(tag: Tag, position: int) -> bool:
    text = tag.get_text().strip()
    if text not in ("+", "-"):
        raise ParseError(f"Garbage in voting list near element {position}: {text!r}")
    return text == "+"
