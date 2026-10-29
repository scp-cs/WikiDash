"""A user's profile page (https://www.wikidot.com/user:info/<name>)."""

import re
from datetime import UTC, datetime

from bs4 import Tag

from wikidash.errors import ParseError, UserNotFoundError
from wikidash.user_models import User, UserActivity

from .html import attr, parse_page

# Labels (dt) of the profile's definition list -> field name. A label may match
# several patterns; the last match wins, as in the original.
_LABELS = {
    "real_name": re.compile(r"Real name", re.IGNORECASE),
    "gender": re.compile(r"Gender", re.IGNORECASE),
    "birthday": re.compile(r"Birthday", re.IGNORECASE),
    "from": re.compile(r"From", re.IGNORECASE),
    "website": re.compile(r"Website", re.IGNORECASE),
    "since": re.compile(r"Wikidot User since:", re.IGNORECASE),
    "bio": re.compile(r"About", re.IGNORECASE),
    "account_type": re.compile(r"Account type", re.IGNORECASE),
    "karma": re.compile(r"Karma level", re.IGNORECASE),
}

# "very high" must be tested before "high" (it contains it).
_ACTIVITY_LEVELS = (
    (re.compile(r"very high", re.IGNORECASE), UserActivity.VERY_HIGH),
    (re.compile(r"high", re.IGNORECASE), UserActivity.HIGH),
    (re.compile(r"medium", re.IGNORECASE), UserActivity.MEDIUM),
    (re.compile(r"low", re.IGNORECASE), UserActivity.LOW),
    (re.compile(r"none", re.IGNORECASE), UserActivity.NONE),
    (re.compile(r"guru", re.IGNORECASE), UserActivity.GURU),
)

_USER_ID_FROM_ONCLICK = re.compile(
    r"^WIKIDOT\.modules\.UserInfoModule\.listeners\.(?:addContact|flagUser)\(event,(\d+)\)$",
    re.IGNORECASE,
)
_DATE = re.compile(r"(\d{1,2}) (\w+) (\d{4})(?:,? (\d{1,2}):(\d{2}))?")


def parse_user_profile(html: str, username: str, fetched_at_ms: int) -> User:
    soup = parse_page(html)
    content = soup.select_one("div.col-md-9")
    if content is None:
        error = soup.select_one("div.error-block")
        if error is not None and error.get_text().strip().lower() == "user does not exist.":
            raise UserNotFoundError(f"User {username} does not exist")
        raise ParseError("Profile page has no div.col-md-9")

    title = content.select_one("h1.profile-title")
    details = content.select_one("dl.dl-horizontal")
    if title is None or details is None:
        raise ParseError("Profile page has no title or details list")

    labels, values = details.find_all("dt"), details.find_all("dd")
    if len(labels) != len(values):
        raise ParseError(f"Profile details are unbalanced: {len(labels)} != {len(values)}")

    found: dict[str, str] = {}
    for label, value in zip(labels, values, strict=True):
        for field, pattern in _LABELS.items():
            if pattern.search(label.get_text()):
                found[field] = value.get_text().strip()

    if "since" not in found:
        raise ParseError("Profile has no 'Wikidot User since'")
    since = parse_wikidot_date(found["since"])
    if since is None:
        raise ParseError(f"Unreadable registration date: {found['since']!r}")
    birthday = parse_wikidot_date(found["birthday"]) if "birthday" in found else None

    return User(
        user_id=_find_user_id(content, username),
        username=username,
        full_name=title.get_text().strip(),
        wikidot_user_since=since,
        fetched_at=fetched_at_ms,
        activity=_parse_activity(found.get("karma")),
        real_name=found.get("real_name"),
        gender=found.get("gender"),
        birthday=None if birthday is None else int(birthday * 1000),
        location=found.get("from"),
        website=found.get("website"),
        bio=found.get("bio"),
        account_type=found.get("account_type"),
    )


def parse_wikidot_date(text: str) -> float | None:
    """Unix seconds of e.g. '6 Sep 2022, 16:33' (read as UTC), or None if unreadable.

    TODO: verify the exact format and time zone against a live profile page.
    """
    match = _DATE.search(text)
    if match is None:
        return None
    day, month, year, hour, minute = match.groups()
    for month_format in ("%b", "%B"):
        try:
            moment = datetime.strptime(f"{day} {month} {year}", f"%d {month_format} %Y")
        except ValueError:
            continue
        moment = moment.replace(hour=int(hour or 0), minute=int(minute or 0), tzinfo=UTC)
        return moment.timestamp()
    return None


def _parse_activity(text: str | None) -> UserActivity:
    for pattern, level in _ACTIVITY_LEVELS:
        if text is not None and pattern.search(text):
            return level
    return UserActivity.UNKNOWN


def _find_user_id(content: Tag, username: str) -> int:
    for link in content.find_all("a"):
        match = _USER_ID_FROM_ONCLICK.search(attr(link, "onclick") or "")
        if match:
            return int(match.group(1))
    raise ParseError(f"Can't determine user id of {username}")
