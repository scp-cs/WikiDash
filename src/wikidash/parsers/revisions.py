"""Page revision list and revision source (ajax modules)."""

import re

from wikidash.models import PageRevision

from .html import first_int, parse_fragment, timestamp
from .users import UserSink, ignore_users, user_id_of

_WHITESPACE = re.compile(r"\s+")

# Column layout of history/PageRevisionListModule's table.
_COL_REVISION = 0
_COL_FLAGS = 2
_COL_GLOBAL_REVISION = 3  # the id is inside an onclick handler
_COL_AUTHOR = 4
_COL_DATE = 5
_COL_COMMENTARY = 6
_MIN_COLUMNS = 7


def parse_revision_list(body: str, on_user: UserSink = ignore_users) -> list[PageRevision]:
    """Parse one page of the revision table. Malformed rows are skipped."""
    rows = parse_fragment(body).find_all("tr")[1:]  # first row is the header
    revisions: list[PageRevision] = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < _MIN_COLUMNS:
            continue

        revision = first_int(cells[_COL_REVISION].get_text())
        link = cells[_COL_GLOBAL_REVISION].find("a")
        global_revision = first_int(str(link.get("onclick", ""))) if link else None
        if revision is None or global_revision is None:
            continue

        revisions.append(
            PageRevision(
                revision=revision,
                global_revision=global_revision,
                author=user_id_of(cells[_COL_AUTHOR], on_user),
                stamp=timestamp(cells[_COL_DATE].find("span")),
                flags=_WHITESPACE.sub(" ", cells[_COL_FLAGS].get_text().strip()),
                commentary=cells[_COL_COMMENTARY].get_text().strip(),
            )
        )
    return revisions


def parse_revision_source(body: str) -> str:
    """Wikitext of one revision (history/PageSourceModule)."""
    div = parse_fragment(body).select_one("div.page-source")
    return div.get_text() if div else ""
