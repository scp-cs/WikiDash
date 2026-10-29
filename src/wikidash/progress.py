"""Progress and error reporting shared by the sync steps."""

import threading
from enum import IntEnum
from typing import Protocol


class Status(IntEnum):
    """Phase of a run. Numeric values are part of the SCUTTLE protocol."""

    BUILDING_SITEMAP = 0
    PAGES_MAIN = 1
    FORUMS_MAIN = 2
    PAGES_PENDING = 3
    FILES_PENDING = 4
    COMPRESSING = 5
    FATAL_ERROR = 6
    OTHER = 7


class ErrorKind(IntEnum):
    """What went wrong. Numeric values are part of the SCUTTLE protocol."""

    CLIENT_OFFLINE = 0
    MALFORMED_SITEMAP = 1
    VOTE_FETCH = 2
    FILE_FETCH = 3
    LOCK_STATUS_FETCH = 4
    FORUM_LIST_FETCH = 5
    FORUM_POST_FETCH = 6
    FILE_META_FETCH = 7
    FILE_UNLINK = 8
    FORUM_COUNT_MISMATCH = 9
    WIKIDOT_INTERNAL = 10
    # 11 was a joke error kind in the original; keep the numbering stable.
    META_MISSING = 12
    GIVING_UP = 13
    TOKEN_INVALIDATED = 14


class Reporter(Protocol):
    """Receives non-fatal errors as they happen (e.g. to forward them to SCUTTLE)."""

    def error(self, kind: ErrorKind, name: str | None = None, message: str = "") -> None: ...


class NullReporter:
    def error(self, kind: ErrorKind, name: str | None = None, message: str = "") -> None:
        pass


class StatusSink(NullReporter):
    """Receives the run's progress; this base class ignores everything.

    `ScuttleConnector` overrides it to forward progress to SCUTTLE.
    """

    def handshake(self) -> None:
        pass

    def preflight(self, total: int) -> None:
        pass

    def progress(
        self, status: Status, done: int | None = None, postponed: int | None = None
    ) -> None:
        pass

    def finish(self) -> None:
        pass


class Counters:
    """Thread-safe done/postponed counters of the page phase."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.done = 0
        self.postponed = 0

    def page_done(self) -> None:
        with self._lock:
            self.done += 1

    def page_postponed(self) -> None:
        with self._lock:
            self.postponed += 1
