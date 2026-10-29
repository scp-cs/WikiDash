"""Wikidot's ajax-module-connector: token handling and module calls."""

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from .errors import WikidotError
from .http import HttpClient
from .logging import create_logger

log = create_logger(__name__)

TOKEN_COOKIE = "wikidot_token7"
WRONG_TOKEN = "wrong_token7"
# Wikidot invalidates our token when we are too aggressive; back off first.
TOKEN_COOLDOWN_SECONDS = 30.0
_FORM = {"Content-Type": "application/x-www-form-urlencoded"}


class WikidotAjax:
    """Calls ajax modules of one wiki, recovering from invalidated tokens."""

    def __init__(
        self,
        client: HttpClient,
        wiki_url: str,
        *,
        cooldown: float = TOKEN_COOLDOWN_SECONDS,
        sleep: Callable[[float], None] = time.sleep,
        on_token_invalidated: Callable[[], None] | None = None,
    ) -> None:
        self._client = client
        self._wiki_url = wiki_url
        self._connector_url = f"{wiki_url}/ajax-module-connector.php"
        self._cooldown = cooldown
        self._sleep = sleep
        self._on_token_invalidated = on_token_invalidated
        # Threads that hit wrong_token7 queue up here; only the first one of a
        # generation refreshes the token, the rest just retry with the new one.
        self._refresh_lock = threading.Lock()
        self._token_generation = 0

    def call(
        self,
        module: str,
        *,
        allow_errors: bool = False,
        headers: dict[str, str] | None = None,
        **params: Any,
    ) -> dict[str, Any]:
        """Call `module`; returns the decoded JSON response.

        A non-ok status raises WikidotError, unless `allow_errors` (then the
        caller inspects `status`/`message` itself).
        """
        while True:
            generation = self._token_generation
            response = self._post(module, params, headers)
            status = response.get("status")
            if status == "ok":
                return response
            if status == WRONG_TOKEN:
                self._refresh_token(generation)
                continue
            if allow_errors:
                return response
            raise WikidotError(str(status), str(response.get("message", "")))

    def ensure_token(self) -> str:
        """Current token; visits the wiki to obtain one if we have none."""
        token = self._client.get_cookie(TOKEN_COOKIE)
        if token is None:
            self._client.get(f"{self._wiki_url}/system:recent-changes", follow_redirects=False)
            token = self._client.get_cookie(TOKEN_COOKIE)
        if token is None:
            raise WikidotError("no_token", "Wikidot did not hand out a token")
        return token

    def _post(
        self, module: str, params: dict[str, Any], headers: dict[str, str] | None
    ) -> dict[str, Any]:
        form = {**params, "moduleName": module, TOKEN_COOKIE: self.ensure_token()}
        request_headers = {**_FORM, "Referer": self._wiki_url, **(headers or {})}
        body = self._client.post(self._connector_url, data=form, headers=request_headers)
        decoded: dict[str, Any] = json.loads(body)
        return decoded

    def _refresh_token(self, seen_generation: int) -> None:
        with self._refresh_lock:
            if self._token_generation != seen_generation:
                return  # another thread already refreshed it while we waited
            log.error("Wikidot invalidated our token, waiting %ss", self._cooldown)
            if self._on_token_invalidated:
                self._on_token_invalidated()
            self._sleep(self._cooldown)
            self._client.delete_cookie(TOKEN_COOKIE)
            self.ensure_token()
            self._token_generation += 1
