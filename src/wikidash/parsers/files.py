"""Page file list and file information (ajax modules)."""

import re

from bs4 import Tag

from wikidash.errors import ParseError
from wikidash.models import FileMeta

from .html import attr, parse_fragment, timestamp
from .users import UserSink, ignore_users, user_id_of

_FILE_ROW_ID = re.compile(r"file-row-(\d+)", re.IGNORECASE)
_SIZE_IN_BYTES = re.compile(r"(\d+) bytes", re.IGNORECASE)

# Row order of files/FileInformationWinModule's table; the value is in column 1.
_ROW_NAME, _ROW_URL, _ROW_SIZE, _ROW_MIME, _ROW_CONTENT, _ROW_UPLOADER, _ROW_DATE = range(7)


def parse_file_list(body: str) -> list[int]:
    """File ids on one page of files/PageFilesModule."""
    ids: list[int] = []
    for row in parse_fragment(body).find_all("tr"):
        match = _FILE_ROW_ID.search(attr(row, "id") or "")
        if match:
            ids.append(int(match.group(1)))
    return ids


def parse_file_info(file_id: int, body: str, on_user: UserSink = ignore_users) -> FileMeta:
    rows = parse_fragment(body).find_all("tr")
    if len(rows) <= _ROW_DATE:
        raise ParseError(f"File {file_id}: expected 7 info rows, got {len(rows)}")

    def value_cell(index: int) -> Tag:
        cells = rows[index].find_all("td")
        if len(cells) < 2:
            raise ParseError(f"File {file_id}: row {index} has no value column")
        return cells[1]

    link = value_cell(_ROW_URL).find("a")
    url = attr(link, "href")
    if url is None:
        raise ParseError(f"File {file_id}: no download link")

    size_text = value_cell(_ROW_SIZE).get_text()
    size_in_bytes = _SIZE_IN_BYTES.search(size_text)

    return FileMeta(
        file_id=file_id,
        name=value_cell(_ROW_NAME).get_text().strip(),
        url=url,
        size=size_text.strip(),
        size_bytes=int(size_in_bytes.group(1)) if size_in_bytes else None,
        mime=value_cell(_ROW_MIME).get_text().strip(),
        content=value_cell(_ROW_CONTENT).get_text().strip(),
        author=user_id_of(value_cell(_ROW_UPLOADER), on_user),
        stamp=timestamp(value_cell(_ROW_DATE).find("span", class_="odate")),
    )
