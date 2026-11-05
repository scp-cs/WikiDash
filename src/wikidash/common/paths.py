"""Mapping of Wikidot names to safe on-disk names.

Names must stay byte-compatible with archives written by the original WikiComma.
"""

from urllib.parse import unquote

# Characters Windows forbids in file names. '*' and '/' are not escaped by
# `quote()`, so the table spells out every replacement explicitly.
_FORBIDDEN = {
    "\\": "%5C",
    ":": "%3A",
    "*": "%2A",
    "?": "%3F",
    '"': "%22",
    "<": "%3C",
    ">": "%3E",
    "|": "%7C",
    "/": "%2F",
}
_ESCAPE_TABLE = str.maketrans(_FORBIDDEN)

# '.' and '..' are not usable as directory names.
_DOT_REPLACEMENT = "why_did_you_name_me_this_way"
_EMPTY_PAGE = "~"


def reencode_component(name: str) -> str:
    """Decode percent-escapes, then re-escape characters unsafe on disk."""
    return unquote(name).translate(_ESCAPE_TABLE)


def normalize_page_name(name: str) -> str:
    """Page name as used for meta/page file names ('scp:001' -> 'scp_001')."""
    return name.replace(":", "_")


def _avoid_dots(component: str) -> str:
    return _DOT_REPLACEMENT if component in (".", "..") else component


def split_file_path(path: str) -> tuple[str, str]:
    """Split 'page/file name' (from a /local--files/ URL) into safe (page, file)."""
    page, slash, file = path.partition("/")
    if not slash:
        # No page component at all.
        return _EMPTY_PAGE, _avoid_dots(reencode_component(path))
    page_dir = reencode_component(page) if page else _EMPTY_PAGE
    return _avoid_dots(page_dir), _avoid_dots(reencode_component(file))
