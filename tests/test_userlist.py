import json
from pathlib import Path

import httpx

from wikidash.http import HttpClient
from wikidash.parsers.user_profile import parse_user_profile, parse_wikidot_date
from wikidash.user_models import User, UserActivity
from wikidash.userlist import UserList, bucket_of

PROFILE = """
<html><body><div class="col-md-9">
<h1 class="profile-title"> Some User </h1>
<dl class="dl-horizontal">
  <dt>Real name</dt><dd>Real Person</dd>
  <dt>From</dt><dd>Prague</dd>
  <dt>Wikidot User since:</dt><dd>6 Sep 2022, 16:33</dd>
  <dt>Karma level</dt><dd>very high</dd>
  <dt>Account type</dt><dd>free</dd>
</dl>
<a onclick="WIKIDOT.modules.UserInfoModule.listeners.addContact(event,8238973)">add</a>
</div></body></html>
"""

NOW_MS = 1_700_000_000_000


def test_parse_profile() -> None:
    user = parse_user_profile(PROFILE, "some-user", NOW_MS)
    assert (user.user_id, user.username, user.full_name) == (8238973, "some-user", "Some User")
    assert (user.real_name, user.location, user.account_type) == ("Real Person", "Prague", "free")
    assert user.activity is UserActivity.VERY_HIGH  # the old "high" regex hid this level
    assert user.wikidot_user_since == 1662481980  # same value as in the original archive
    assert user.fetched_at == NOW_MS


def test_parse_date() -> None:
    assert parse_wikidot_date("6 Sep 2022, 16:33") == 1662481980
    assert parse_wikidot_date("garbage") is None


def test_user_roundtrip_matches_original_json() -> None:
    raw = {
        "full_name": "choccoMan",
        "username": "choccoman",
        "real_name": "Eugenius Quasimodo Lawchild",
        "from": "the 8th Circle of Torment",
        "website": "http://peepeepoopoo.poop/peenar",
        "wikidot_user_since": 1662481980,
        "account_type": "free",
        "activity": 3,
        "fetched_at": 1791314452852,
        "user_id": 8238973,
    }
    dumped = User.from_dict(raw).to_dict()
    assert dumped == raw and list(dumped) == list(raw)


def make_list(tmp_path: Path, pages: dict[str, str], now_ms: int = NOW_MS) -> UserList:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1].split(":", 2)[-1]
        if name not in pages:
            return httpx.Response(200, text='<div class="error-block">User does not exist.</div>')
        return httpx.Response(200, text=pages[name])

    client = HttpClient(transport=httpx.MockTransport(handler))
    return UserList(tmp_path / "_users", client, cache_seconds=3600, clock=lambda: now_ms / 1000)


def test_register_fetch_and_cache(tmp_path: Path) -> None:
    users = make_list(tmp_path, {"some-user": PROFILE})
    users.register(8238973, "some-user")
    users.register(8238973, "some-user")  # duplicate is ignored
    assert users.pending_count() == 1

    users.fetch_pending()
    assert users.pending_count() == 0
    stored = json.loads((tmp_path / "_users" / f"{bucket_of(8238973)}.json").read_text())
    assert stored["8238973"]["username"] == "some-user"

    # A fresh run with a fresh cache entry queues nothing; a stale one queues again.
    fresh = make_list(tmp_path, {"some-user": PROFILE})
    fresh.register(8238973, "some-user")
    assert fresh.pending_count() == 0
    stale = make_list(tmp_path, {"some-user": PROFILE}, now_ms=NOW_MS + 2 * 3600 * 1000)
    stale.register(8238973, "some-user")
    assert stale.pending_count() == 1


def test_missing_user_is_dropped_from_pending(tmp_path: Path) -> None:
    users = make_list(tmp_path, {})
    users.register(5, "ghost")
    users.fetch_pending()
    assert users.pending_count() == 0
    assert users.get(5) is None
