"""Everything we ask Wikidot, one method per question.

Every call retries transient failures with the single policy from `retry.py`;
a call that still fails raises, and the sync layer decides to postpone it.
"""

import json
import time
from collections.abc import Callable, Hashable, Iterator
from typing import Any

import httpx

from .ajax import WikidotAjax
from .errors import WikidashError
from .forum_models import CategoryInfo, PostInfo, PostRevision, RevisionBody, ThreadInfo
from .http import HttpClient
from .models import FileMeta, PageInfo, PageRevision, UserId
from .parsers import files as file_parsers
from .parsers import forum as forum_parsers
from .parsers import page as page_parsers
from .parsers import revisions as revision_parsers
from .parsers import voters as voter_parsers
from .parsers.html import parse_fragment
from .parsers.users import UserSink, ignore_users
from .retry import retry

REVISIONS_PER_PAGE = 100
# Anything in this tuple is worth another attempt.
TRANSIENT_ERRORS = (WikidashError, httpx.HTTPError, json.JSONDecodeError)


def paginate[T](
    fetch_page: Callable[[int], list[T]],
    *,
    key: Callable[[T], Hashable],
    stop_when: Callable[[T], bool] | None = None,
) -> Iterator[T]:
    """Yield items of pages 1, 2, ... until an empty page or one with nothing new.

    Wikidot answers out-of-range page numbers with the last page again, hence
    the `key` that tells items apart. With `stop_when`, stop (without yielding)
    at the first item it accepts; used to fetch only what is newer than ours.
    """
    seen: set[Hashable] = set()
    page = 1
    while True:
        items = [item for item in fetch_page(page) if key(item) not in seen]
        if not items:
            return
        for item in items:
            if stop_when is not None and stop_when(item):
                return
            seen.add(key(item))
            yield item
        page += 1


def _has_link(response: dict[str, Any]) -> bool:
    """Whether an error message contains a link (Wikidot's way of saying 'you may proceed')."""
    return parse_fragment(str(response.get("message", ""))).find("a") is not None


class WikidotApi:
    def __init__(
        self,
        client: HttpClient,
        ajax: WikidotAjax,
        wiki_url: str,
        *,
        on_user: UserSink = ignore_users,
        attempts: int = 5,
        retry_delay: float = 5.0,
    ) -> None:
        self._client = client
        self._ajax = ajax
        self._url = wiki_url
        self._on_user = on_user
        self._attempts = attempts
        self._retry_delay = retry_delay

    # --- pages ---------------------------------------------------------

    def page_info(self, page_name: str) -> PageInfo:
        url = f"{self._url}/{page_name}/noredirect/true?_ts={int(time.time() * 1000)}"
        html = self._get_text(url, headers={"Referer": self._url})
        return page_parsers.parse_page_info(html)

    def revisions(self, page_id: int, *, newer_than: int | None = None) -> list[PageRevision]:
        """Revision list, newest first. With `newer_than`, only revisions above that number."""
        stop = None if newer_than is None else (lambda rev: rev.revision <= newer_than)
        pages = paginate(lambda page: self._revision_page(page_id, page), key=lambda r: r.revision, stop_when=stop)
        return list(pages)

    def revision_source(self, global_revision: int) -> str:
        body = self._module("history/PageSourceModule", revision_id=global_revision)
        return revision_parsers.parse_revision_source(body)

    def voters(self, page_id: int) -> list[tuple[UserId, bool]] | None:
        body = self._module("pagerate/WhoRatedPageModule", pageId=page_id)
        return voter_parsers.parse_voters(body, self._on_user)

    def is_page_locked(self, page_id: int) -> bool:
        response = self._call("edit/PageEditModule", allow_errors=True, page_id=page_id)
        # An unlocked page offers a link (to start editing); a locked one only a message.
        return not _has_link(response)

    # --- files ---------------------------------------------------------

    def file_ids(self, page_id: int) -> list[int]:
        """Ids of all files attached to a page (stops once a page adds nothing new)."""
        seen: dict[int, None] = {}
        page = 1
        while True:
            body = self._module("files/PageFilesModule", page_id=page_id, page=page)
            new_ids = [i for i in file_parsers.parse_file_list(body) if i not in seen]
            if not new_ids:
                return list(seen)
            seen.update(dict.fromkeys(new_ids))
            page += 1

    def file_info(self, file_id: int) -> FileMeta:
        body = self._module("files/FileInformationWinModule", file_id=file_id)
        return file_parsers.parse_file_info(file_id, body, self._on_user)

    def download(self, url: str) -> bytes:
        return self._with_retry(self._client.get, url, headers={"Referer": self._url})

    # --- forum ---------------------------------------------------------

    def forum_categories(self) -> list[CategoryInfo]:
        html = self._get_text(f"{self._url}/forum/start/hidden/show")
        return forum_parsers.parse_categories(html, self._on_user)

    def threads(self, category_id: int, *, newer_than: int | None = None) -> list[ThreadInfo]:
        """All threads of a category; with `newer_than`, only those with a higher id."""
        stop = None if newer_than is None else (lambda thread: thread.id <= newer_than)
        pages = paginate(lambda page: self.thread_page(category_id, page), key=lambda t: t.id, stop_when=stop)
        return list(pages)

    def thread_page(self, category_id: int, page: int) -> list[ThreadInfo]:
        html = self._get_text(f"{self._url}/forum/c-{category_id}/p/{page}")
        return forum_parsers.parse_threads(html, self._on_user)

    def is_thread_locked(self, thread_id: int) -> bool:
        response = self._call(
            "forum/sub/ForumNewPostFormModule", allow_errors=True, threadId=thread_id, postId=""
        )
        if response.get("status") == "ok":
            return False
        return not _has_link(response)

    def thread_posts(self, thread_id: int) -> list[PostInfo]:
        return list(paginate(lambda page: self._post_page(thread_id, page), key=lambda p: p.id))

    def post_revisions(self, post_id: int) -> list[PostRevision]:
        body = self._module("forum/sub/ForumPostRevisionsModule", postId=post_id)
        return forum_parsers.parse_post_revisions(body, self._on_user)

    def post_revision(self, revision_id: int) -> RevisionBody:
        response = self._call(
            "forum/sub/ForumPostRevisionModule", allow_errors=True, revisionId=revision_id
        )
        if response.get("body") != "ok":
            raise WikidashError(f"Post revision {revision_id}: server said {response}")
        return RevisionBody(title=response["title"], content=response["content"])

    # --- internals -----------------------------------------------------

    def _revision_page(self, page_id: int, page: int) -> list[PageRevision]:
        body = self._module(
            "history/PageRevisionListModule",
            options='{"all": true}',
            page=page,
            perpage=REVISIONS_PER_PAGE,
            page_id=page_id,
        )
        return revision_parsers.parse_revision_list(body, self._on_user)

    def _post_page(self, thread_id: int, page: int) -> list[PostInfo]:
        body = self._module("forum/ForumViewThreadPostsModule", t=thread_id, pageNo=page, order="")
        return forum_parsers.parse_thread_posts(body, self._on_user)

    def _call(self, module: str, **params: Any) -> dict[str, Any]:
        return self._with_retry(lambda: self._ajax.call(module, **params))

    def _module(self, module: str, **params: Any) -> str:
        """HTML body of an ajax module response."""
        return str(self._call(module, **params)["body"])

    def _get_text(self, url: str, **kwargs: Any) -> str:
        data = self._with_retry(self._client.get, url, **kwargs)
        return data.decode("utf-8")

    def _with_retry[T](self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        policy = retry(self._attempts, self._retry_delay, on=TRANSIENT_ERRORS)
        return policy(func)(*args, **kwargs)
