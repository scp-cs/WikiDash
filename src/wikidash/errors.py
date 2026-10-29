"""Exception types shared across the package."""


class WikidashError(Exception):
    """Base class for all errors raised by this package."""


class HttpError(WikidashError):
    def __init__(self, status: int, url: str, body: bytes = b"") -> None:
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url
        self.body = body


class WikidotError(WikidashError):
    """Wikidot's ajax connector answered with a status other than 'ok'."""

    def __init__(self, status: str, message: str) -> None:
        super().__init__(f"Wikidot returned {status}: {message}")
        self.status = status
        self.message = message


class ParseError(WikidashError):
    """Wikidot HTML did not look the way a parser expected."""


class UserNotFoundError(ParseError):
    """The profile page says the user does not exist."""
