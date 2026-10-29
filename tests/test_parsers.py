import pytest

from wikidash.errors import ParseError
from wikidash.parsers.html import parse_fragment
from wikidash.parsers.page import parse_page_info
from wikidash.parsers.revisions import parse_revision_list, parse_revision_source
from wikidash.parsers.users import extract_user
from wikidash.parsers.voters import parse_voters

USER_SPAN = (
    '<span class="printuser"><a href="http://www.wikidot.com/user:info/some-user" '
    'onclick="WIKIDOT.page.listeners.userInfo(123); return false;">Some User</a></span>'
)
DELETED_SPAN = '<span class="printuser deleted" data-id="456">(account deleted)</span>'


def test_extract_user_normal_and_deleted_and_anonymous() -> None:
    user = extract_user(parse_fragment(USER_SPAN).span)
    assert user is not None and (user.user_id, user.username) == (123, "some-user")

    deleted = extract_user(parse_fragment(f"<td>{DELETED_SPAN}</td>").td)
    assert deleted is not None and (deleted.user_id, deleted.username) == (456, None)

    assert extract_user(parse_fragment("<span>guest</span>").span) is None
    assert extract_user(None) is None


REVISIONS = f"""
<table>
<tr><th>rev</th><th></th><th>flags</th><th></th><th>by</th><th>date</th><th>comment</th></tr>
<tr>
  <td>5.</td><td>buttons</td><td> N  S </td>
  <td><a onclick="showVersion(9001)">v</a></td>
  <td>{USER_SPAN}</td>
  <td><span class="odate time_1600000000">date</span></td>
  <td> fixed typo </td>
</tr>
<tr><td>junk</td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
</table>
"""


def test_parse_revision_list() -> None:
    seen: list[tuple[int, str]] = []
    revisions = parse_revision_list(REVISIONS, lambda i, n: seen.append((i, n)))
    assert len(revisions) == 1
    rev = revisions[0]
    assert (rev.revision, rev.global_revision, rev.author, rev.stamp) == (5, 9001, 123, 1600000000)
    assert (rev.flags, rev.commentary) == ("N S", "fixed typo")
    assert seen == [(123, "some-user")]


def test_revision_to_dict_omits_missing_stamp() -> None:
    rev = parse_revision_list(REVISIONS.replace("time_1600000000", "x"))[0]
    assert "stamp" not in rev.to_dict()


def test_parse_revision_source() -> None:
    assert parse_revision_source('<div class="page-source">a\nb</div>') == "a\nb"
    assert parse_revision_source("<p>nothing</p>") == ""


def test_parse_voters() -> None:
    body = f"<div>{USER_SPAN}<span>+</span><br/>{DELETED_SPAN}<span> - </span><br/></div>"
    assert parse_voters(body) == [(123, True), (456, False)]


def test_parse_voters_without_list() -> None:
    assert parse_voters("<p>nobody</p>") is None


@pytest.mark.parametrize(
    "body",
    [
        f"<div>{USER_SPAN}<br/></div>",  # no vote
        f"<div>{USER_SPAN}<span>?</span><br/></div>",  # garbage vote
        f"<div>{USER_SPAN}<span>+</span><span>+</span></div>",  # extra span
    ],
)
def test_parse_voters_malformed(body: str) -> None:
    with pytest.raises(ParseError):
        parse_voters(body)


PAGE = """
<html><head><script>
  WIKIREQUEST.info.pageId = 777;
</script></head><body>
<div id="main-content"><div id="breadcrumbs"><a href="/top">top</a><a href="/scp-series">s</a></div>
<div id="page-title"> My Title </div>
<span class="rate-points">rating: <span class="number">+42</span></span>
<div class="page-tags"><span><a href="/system:page-tags/tag/safe#pages">safe</a>
<a href="/system:page-tags/tag/a%20b">a b</a></span></div>
<a id="discuss-button" href="/forum/t-555/discuss">discuss</a>
</div></body></html>
"""


def test_parse_page_info() -> None:
    info = parse_page_info(PAGE)
    assert info.page_id == 777
    assert info.title == "My Title"
    assert info.rating == 42
    assert info.forum_thread == 555
    assert info.tags == ["safe", "a b"]
    assert info.parent == "scp-series"


def test_parse_page_info_empty() -> None:
    info = parse_page_info("<html><body></body></html>")
    assert info.page_id is None and info.tags == [] and info.parent is None
