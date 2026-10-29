"""Cached Wikidot user profiles, stored in buckets of `id >> 13` per file.

Parsers report every user they see through `UserList.register`; the runner
later calls `fetch_pending` to download the profiles that are missing or stale.
Nothing here runs in the background.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from .errors import UserNotFoundError
from .http import BROWSER_USER_AGENT, HttpClient
from .logging import create_logger
from .parsers.user_profile import parse_user_profile
from .store import PersistentSet, read_json, write_json
from .user_models import User

log = create_logger(__name__)

BUCKET_SHIFT = 13
PROFILE_URL = "https://www.wikidot.com/user:info/{username}"


def bucket_of(user_id: int) -> int:
    return user_id >> BUCKET_SHIFT


class UserList:
    def __init__(
        self,
        folder: Path,
        client: HttpClient,
        *,
        cache_seconds: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._folder = folder
        self._client = client
        self._cache_ms = cache_seconds * 1000
        self._clock = clock
        self._lock = threading.RLock()
        self._buckets: dict[int, dict[str, Any]] = {}
        self._seen: set[tuple[int | None, str]] = set()
        # [user_id or None, username] pairs still to download.
        self._pending = PersistentSet(folder / "pending.json")

    # --- reading and writing -------------------------------------------

    def get(self, user_id: int) -> User | None:
        with self._lock:
            raw = self._bucket(bucket_of(user_id)).get(str(user_id))
        return None if raw is None else User.from_dict(raw)

    def put(self, user: User) -> None:
        with self._lock:
            bucket = self._bucket(bucket_of(user.user_id))
            bucket[str(user.user_id)] = user.to_dict()
            write_json(self._bucket_path(bucket_of(user.user_id)), bucket)

    def _bucket(self, number: int) -> dict[str, Any]:
        if number not in self._buckets:
            path = self._bucket_path(number)
            self._buckets[number] = read_json(path) if path.exists() else {}
        return self._buckets[number]

    def _bucket_path(self, number: int) -> Path:
        return self._folder / f"{number}.json"

    # --- discovering and fetching users --------------------------------

    def register(self, user_id: int, username: str) -> None:
        """Note that a user exists; queue a download unless we have a fresh copy."""
        key = (user_id, username)
        with self._lock:
            if key in self._seen:
                return
            self._seen.add(key)
            if not self._is_stale(self.get(user_id)):
                return
            self._pending.add([user_id, username])

    def fetch_pending(self, workers: int = 4) -> None:
        """Download every queued profile; failures stay queued for the next run."""
        with ThreadPoolExecutor(max_workers=workers) as pool:
            list(pool.map(self._fetch_queued, self._pending.to_list()))
        self.save()

    def fetch(self, username: str) -> User:
        """Download one profile now and store it."""
        url = PROFILE_URL.format(username=username)
        html = self._client.get(url, headers={"User-Agent": BROWSER_USER_AGENT}).decode("utf-8")
        user = parse_user_profile(html, username, fetched_at_ms=int(self._clock() * 1000))
        self.put(user)
        return user

    def save(self) -> None:
        self._pending.save()

    def pending_count(self) -> int:
        return len(self._pending)

    def _fetch_queued(self, entry: list[Any]) -> None:
        user_id, username = entry
        try:
            self.fetch(username)
        except UserNotFoundError:
            log.warning("User %s<%s> does not exist, dropping", username, user_id)
        except Exception as err:  # noqa: BLE001 - one bad profile must not stop the rest
            log.error("Could not fetch user %s<%s>: %s", username, user_id, err)
            return
        self._pending.discard(entry)

    def _is_stale(self, user: User | None) -> bool:
        return user is None or user.fetched_at + self._cache_ms < self._clock() * 1000
