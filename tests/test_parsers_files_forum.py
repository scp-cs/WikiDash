import pytest

from wikidash.errors import ParseError
from wikidash.parsers.files import parse_file_info, parse_file_list
from wikidash.parsers.forum import (
    parse_categories,
    parse_post_revisions,
    parse_thread_posts,
    parse_threads,
)

USER = (
    '<span class="printuser"><a href="/user:info/bob" '
    'onclick="WIKIDOT.page.listeners.userInfo(7); return false;">Bob</a></span>'
)
ODATE = '<span class="odate time_1600000000">date</span>'


def test_parse_file_list() -> None:
    body = '<table><tr id="file-row-11"></tr><tr id="file-row-12"></tr><tr></tr></table>'
    assert parse_file_list(body) == [11, 12]


def _file_row(label: str, value: str) -> str:
    return f"<tr><td>{label}</td><td>{value}</td></tr>"


FILE_INFO = "<table>" + "".join(
    [
        _file_row("Name", " pic.png "),
        _file_row("URL", '<a href="http://w.wikidot.com/local--files/p/pic.png">u</a>'),
        _file_row("Size", "45.47 kB (46561 Bytes)"),
        _file_row("Mime", "image/png"),
        _file_row("Content", "PNG image data"),
        _file_row("Uploader", USER),
        _file_row("Date", ODATE),
    ]
) + "</table>"


def test_parse_file_info() -> None:
    meta = parse_file_info(5, FILE_INFO)
    assert (meta.name, meta.url) == ("pic.png", "http://w.wikidot.com/local--files/p/pic.png")
    assert (meta.size, meta.size_bytes) == ("45.47 kB (46561 Bytes)", 46561)
    assert (meta.mime, meta.content) == ("image/png", "PNG image data")
    assert (meta.author, meta.stamp, meta.internal_version) == (7, 1600000000, 1)


def test_parse_file_info_rejects_bad_layout() -> None:
    with pytest.raises(ParseError):
        parse_file_info(5, "<table><tr><td>a</td><td>b</td></tr></table>")


CATEGORIES = f"""
<div class="forum-start-box"><table>
<tr class="head"><td>h</td></tr>
<tr><td class="name"><div class="title"><a href="/forum/c-33/general">General</a></div>
    <div class="description"> Talk </div></td>
  <td class="threads">4</td><td class="posts">20</td>
  <td class="last">{ODATE} by {USER}</td></tr>
</table></div>
"""


def test_parse_categories() -> None:
    (cat,) = parse_categories(CATEGORIES)
    assert (cat.id, cat.title, cat.description) == (33, "General", "Talk")
    assert (cat.threads, cat.posts, cat.last, cat.last_user) == (4, 20, 1600000000, 7)


def test_parse_categories_without_forum() -> None:
    assert parse_categories("<html></html>") == []


def _thread_row(title_prefix: str, last_cell: str) -> str:
    return f"""<tr><td class="name"><div class="title">{title_prefix}<a href="/forum/t-99/x">Topic</a></div>
    <div class="description">d</div></td>
    <td class="started">{ODATE}{USER}</td><td class="posts">3</td>
    <td class="last">{last_cell}</td></tr>"""


def test_parse_threads_with_and_without_last_post() -> None:
    html = (
        '<div id="page-content"><table class="table"><tr class="head"></tr>'
        + _thread_row("Sticky: ", f"{ODATE}{USER}")
        + _thread_row("", "")
        + "</table></div>"
    )
    sticky, plain = parse_threads(html)
    assert (sticky.id, sticky.title, sticky.sticky, sticky.posts_num) == (99, "Topic", True, 3)
    assert (sticky.started, sticky.started_user) == (1600000000, 7)
    assert (sticky.last, sticky.last_user) == (1600000000, 7)
    assert plain.sticky is False and plain.last is None and plain.last_user is None


def test_parse_threads_without_table_fails() -> None:
    with pytest.raises(ParseError):
        parse_threads("<div id='page-content'></div>")


def _post(post_id: int, title: str, children: str = "", changes: str = "") -> str:
    return f"""<div class="post-container"><div class="post" id="post-{post_id}">
    <div class="head"><div class="title">{title}</div><div class="info">{USER}{ODATE}</div></div>
    <div class="content"><p>body {post_id}</p></div>{changes}</div>{children}</div>"""


def test_parse_thread_posts_builds_tree() -> None:
    changes = f'<div class="changes">edited {ODATE}{USER}</div>'
    body = _post(1, "Root", children=_post(2, "Reply"), changes=changes) + _post(3, "Other")
    first, second = parse_thread_posts(body)
    assert (first.id, first.title, first.poster, first.stamp) == (1, "Root", 7, 1600000000)
    assert first.content == "<p>body 1</p>"
    assert (first.last_edit, first.last_edit_by) == (1600000000, 7)
    assert [c.id for c in first.children] == [2]
    assert second.id == 3 and second.last_edit is None and second.children == []


def test_parse_thread_posts_rejects_broken_post() -> None:
    with pytest.raises(ParseError):
        parse_thread_posts('<div class="post-container"></div>')


def test_parse_post_revisions() -> None:
    body = f"""<table class="table"><tr>
    <td>{USER}</td><td>{ODATE}</td><td><a onclick="showRevision(555)">show</a></td></tr></table>"""
    (rev,) = parse_post_revisions(body)
    assert (rev.id, rev.author, rev.stamp) == (555, 7, 1600000000)
