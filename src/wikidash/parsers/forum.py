"""Forum categories, threads, posts and post revisions."""

import re

from bs4 import Tag
from bs4.element import NavigableString

from wikidash.errors import ParseError
from wikidash.forum_models import (
    CategoryInfo,
    PostInfo,
    PostRevision,
    ThreadInfo,
)

from .html import attr, child_tags, first_int, parse_fragment, parse_page, timestamp
from .users import UserSink, ignore_users, user_id_of

_CATEGORY_ID = re.compile(r"forum/c-(\d+)")
_THREAD_ID = re.compile(r"forum/t-(\d+)")
_POST_ID = re.compile(r"post-(\d+)")


def parse_categories(html: str, on_user: UserSink = ignore_users) -> list[CategoryInfo]:
    """Categories on /forum/start (all tables of `div.forum-start-box`)."""
    box = parse_page(html).select_one("div.forum-start-box")
    if box is None:
        return []

    categories: list[CategoryInfo] = []
    for row in _data_rows(box.find_all("tr")):
        name = row.select_one("td.name")
        threads = row.select_one("td.threads")
        posts = row.select_one("td.posts")
        last = row.select_one("td.last")
        if name is None or threads is None or posts is None or last is None:
            continue

        link = _required(name.select_one("div.title a"), "category link")
        categories.append(
            CategoryInfo(
                id=_match_id(_CATEGORY_ID, attr(link, "href"), "category id"),
                title=link.get_text().strip(),
                description=_required(name.select_one("div.description"), "description")
                .get_text()
                .strip(),
                threads=_number(threads.get_text()),
                posts=_number(posts.get_text()),
                last=timestamp(last.select_one("span.odate")),
                last_user=user_id_of(last, on_user),
            )
        )
    return categories


def parse_threads(html: str, on_user: UserSink = ignore_users) -> list[ThreadInfo]:
    """One page of a category's thread list (/forum/c-<id>/p/<page>)."""
    table = parse_page(html).select_one("div#page-content table.table")
    if table is None:
        raise ParseError("Thread list table not found")

    threads: list[ThreadInfo] = []
    for row in _data_rows(table.find_all("tr")):
        name = row.select_one("td.name")
        started = row.select_one("td.started")
        posts = row.select_one("td.posts")
        last = row.select_one("td.last")
        if name is None or started is None or posts is None or last is None:
            continue

        title = _required(name.select_one("div.title"), "thread title")
        link = _required(title.find("a"), "thread link")
        # A thread without posts has an empty "last" cell.
        has_last = len(last.contents) > 1
        started_stamp = timestamp(started.select_one("span.odate"))
        if started_stamp is None:
            raise ParseError("Thread without start date")

        threads.append(
            ThreadInfo(
                id=_match_id(_THREAD_ID, attr(link, "href"), "thread id"),
                title=link.get_text().strip(),
                description=_required(name.select_one("div.description"), "description")
                .get_text()
                .strip(),
                posts_num=_number(posts.get_text()),
                sticky=_is_sticky(title),
                started=started_stamp,
                started_user=user_id_of(started, on_user),
                last=timestamp(last.select_one("span.odate")) if has_last else None,
                last_user=user_id_of(last, on_user) if has_last else None,
            )
        )
    return threads


def parse_thread_posts(body: str, on_user: UserSink = ignore_users) -> list[PostInfo]:
    """Top-level posts of one page of forum/ForumViewThreadPostsModule."""
    return [
        _parse_post(container, on_user)
        for container in child_tags(parse_fragment(body))
        if attr(container, "class") == "post-container"
    ]


def parse_post_revisions(body: str, on_user: UserSink = ignore_users) -> list[PostRevision]:
    """Revision list of one post (forum/sub/ForumPostRevisionsModule)."""
    table = parse_fragment(body).select_one("table.table")
    if table is None:
        raise ParseError("Post revision table not found")

    revisions: list[PostRevision] = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) < 3:
            continue
        stamp = timestamp(cells[1].select_one("span.odate"))
        link = cells[2].find("a")
        revision_id = first_int(attr(link, "onclick"))
        if stamp is None or revision_id is None:
            raise ParseError("Malformed post revision row")
        revisions.append(
            PostRevision(id=revision_id, author=user_id_of(cells[0], on_user), stamp=stamp)
        )
    return revisions


def _parse_post(container: Tag, on_user: UserSink) -> PostInfo:
    post: Tag | None = None
    child_containers: list[Tag] = []
    for tag in child_tags(container):
        css_class = attr(tag, "class")
        if css_class == "post":
            post = tag
        elif css_class == "post-container":
            child_containers.append(tag)
    if post is None:
        raise ParseError("post-container without a post")

    info = _required(post.select_one("div.head div.info"), "post info")
    content = _required(post.select_one("div.content"), "post content")
    title = _required(post.select_one("div.title"), "post title")
    stamp = timestamp(info.select_one("span.odate"))
    if stamp is None:
        raise ParseError("Post without date")

    parsed = PostInfo(
        id=_match_id(_POST_ID, attr(post, "id"), "post id"),
        title=title.get_text().strip(),
        poster=user_id_of(info, on_user),
        content=content.decode_contents(),
        stamp=stamp,
        children=[_parse_post(child, on_user) for child in child_containers],
    )

    changes = post.select_one("div.changes")
    if changes is not None:
        parsed.last_edit = timestamp(changes.select_one("span.odate"))
        parsed.last_edit_by = user_id_of(changes, on_user)
    return parsed


def _data_rows(rows: list[Tag]) -> list[Tag]:
    """Table rows without the header row."""
    if rows and attr(rows[0], "class") == "head":
        return rows[1:]
    return rows


def _is_sticky(title: Tag) -> bool:
    # Sticky threads have a text label before the title link; weak but all there is.
    first = title.contents[0] if title.contents else None
    return isinstance(first, NavigableString) and first.strip() != ""


def _required(tag: Tag | None, what: str) -> Tag:
    if tag is None:
        raise ParseError(f"Forum HTML: {what} not found")
    return tag


def _match_id(pattern: re.Pattern[str], text: str | None, what: str) -> int:
    match = pattern.search(text or "")
    if match is None:
        raise ParseError(f"Forum HTML: {what} not found in {text!r}")
    return int(match.group(1))


def _number(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError as err:
        raise ParseError(f"Forum HTML: expected a number, got {text!r}") from err
