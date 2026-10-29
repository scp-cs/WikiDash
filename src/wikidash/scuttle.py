"""Progress reports to SCUTTLE (https://github.com/scp-cs/translatordb_web)."""

import json
import logging
from enum import IntEnum
from typing import Any

import httpx

from .progress import ErrorKind, Status, StatusSink

from .logging import create_logger

log = create_logger(__name__)

STATUS_PATH = "/backup/status"
REQUEST_TIMEOUT = 10.0


class MessageType(IntEnum):
    """Numeric values are part of the SCUTTLE protocol."""

    HANDSHAKE = 0
    PREFLIGHT = 1
    PROGRESS = 2
    ERROR_FATAL = 3
    ERROR_NONFATAL = 4
    FINISH_SUCCESS = 5
    PAGE_DONE = 6
    PAGE_POSTPONED = 7


class ScuttleConnector(StatusSink):
    """Best effort: a SCUTTLE outage never interrupts a backup."""

    def __init__(
        self, tag: str, address: str, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._tag = tag
        self._url = address + STATUS_PATH
        self._client = httpx.Client(timeout=REQUEST_TIMEOUT, transport=transport)

    def handshake(self) -> None:
        self._send(MessageType.HANDSHAKE)

    def preflight(self, total: int) -> None:
        self._send(MessageType.PREFLIGHT, total=total)

    def progress(
        self, status: Status, done: int | None = None, postponed: int | None = None
    ) -> None:
        self._send(MessageType.PROGRESS, status=int(status), done=done, postponed=postponed)

    def error(self, kind: ErrorKind, name: str | None = None, message: str = "") -> None:
        self._send(
            MessageType.ERROR_NONFATAL, errorKind=int(kind), name=name, errorStr=message or None
        )

    def fatal(self, message: str) -> None:
        self._send(MessageType.ERROR_FATAL, status=int(Status.FATAL_ERROR), errorStr=message)

    def finish(self) -> None:
        self._send(MessageType.FINISH_SUCCESS)

    def _send(self, kind: MessageType, **data: Any) -> None:
        payload = {"tag": self._tag, "type": int(kind)}
        payload.update({key: value for key, value in data.items() if value is not None})
        # SCUTTLE expects the JSON text to be JSON-encoded once more (the original
        # sent JSON.stringify(JSON.stringify(...))), so do the same.
        body = json.dumps(json.dumps(payload))
        try:
            self._client.post(self._url, content=body)
        except httpx.HTTPError as err:
            log.warning("SCUTTLE (%s) unreachable: %s", self._tag, err)
