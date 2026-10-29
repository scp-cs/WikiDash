"""Incremental sync of the forum: categories -> threads -> posts -> post revisions."""

from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from .api import TRANSIENT_ERRORS
from .errors import HttpError
from .forum_models import (
    FORUM_CATEGORY_METADATA_VERSION,
    FORUM_THREAD_METADATA_VERSION,
    CategoryInfo,
    CategoryMeta,
    PostInfo,
    PostRevision,
    RevisionBody,
    StoredPost,
    StoredPostRevision,
    ThreadInfo,
    ThreadMeta,
)
from .forum_store import LATEST, ForumStore, KnownHtml
from .logging import create_logger
from .progress import ErrorKind, NullReporter, Reporter

log = create_logger(__name__)

THREAD_WORKERS = 3


class ForumSource(Protocol):
    def forum_categories(self) -> list[CategoryInfo]: ...
    def thread_page(self, category_id: int, page: int) -> list[ThreadInfo]: ...
    def is_thread_locked(self, thread_id: int) -> bool: ...
    def thread_posts(self, thread_id: int) -> list[PostInfo]: ...
    def post_revisions(self, post_id: int) -> list[PostRevision]: ...
    def post_revision(self, revision_id: int) -> RevisionBody: ...


class ForumSyncer:
    def __init__(
        self,
        store: ForumStore,
        source: ForumSource,
        reporter: Reporter | None = None,
        workers: int = THREAD_WORKERS,
    ) -> None:
        self._store = store
        self._source = source
        self._reporter = reporter or NullReporter()
        self._workers = workers

    def sync_all(self) -> bool:
        """Sync every category. Returns False if some part must be retried next run."""
        try:
            categories = self._source.forum_categories()
        except TRANSIENT_ERRORS as err:
            log.error("Could not list forum categories: %s", err)
            self._reporter.error(ErrorKind.FORUM_LIST_FETCH, message=str(err))
            return False
        # Sync every category even if one fails, hence a list rather than a lazy `all`.
        results = [self._sync_category(category) for category in categories]
        return all(results)

    # --- categories ----------------------------------------------------

    def _sync_category(self, info: CategoryInfo) -> bool:
        local = self._store.read_category(info.id)
        if (
            local is not None
            and local.last == info.last
            and local.full_scan
            and local.version == FORUM_CATEGORY_METADATA_VERSION
        ):
            return True  # nothing new since the last complete scan

        full_scan = local.full_scan if local else False
        page = local.last_page if local else 0

        while True:
            page += 1
            log.info("Fetching threads of category %s, page %s", info.id, page)
            threads = self._source.thread_page(info.id, page)
            results = self._sync_threads(info.id, threads)

            if None in results:  # a thread failed; retry this page next run
                self._store.write_category(_category_meta(info, full_scan, page - 1))
                return False

            updated = True in results
            if not threads or (not updated and full_scan):
                self._store.write_category(_category_meta(info, True, 0))
                return True
            self._store.write_category(_category_meta(info, full_scan, page))

    # --- threads -------------------------------------------------------

    def _sync_threads(self, category_id: int, threads: list[ThreadInfo]) -> list[bool | None]:
        """Per thread: True if it was refetched, False if current, None if it failed."""

        def sync(thread: ThreadInfo) -> bool | None:
            try:
                return self._sync_thread(category_id, thread)
            except TRANSIENT_ERRORS as err:
                log.error("Thread %s failed: %s", thread.id, err)
                self._reporter.error(ErrorKind.FORUM_POST_FETCH, str(thread.id), str(err))
                return None

        with ThreadPoolExecutor(max_workers=self._workers) as pool:
            return list(pool.map(sync, threads))

    def _sync_thread(self, category_id: int, info: ThreadInfo) -> bool:
        local = self._store.read_thread(category_id, info.id)
        known = self._store.known_html(category_id, info.id)
        if local is not None and not self._needs_refetch(local, info, known):
            return False

        log.info("Fetching thread %s (%s)", info.title, info.id)
        meta = ThreadMeta(
            id=info.id,
            title=info.title,
            description=info.description,
            posts_num=info.posts_num,
            sticky=info.sticky,
            started=info.started,
            started_user=info.started_user,
            last=info.last,
            last_user=info.last_user,
            is_locked=self._source.is_thread_locked(info.id),
        )
        old_posts = {post.id: post for post in local.all_posts()} if local else {}
        writer = _PostWriter(self._store, self._source, self._reporter, category_id, info.id, known)
        meta.posts = [writer.store(post, old_posts) for post in self._source.thread_posts(info.id)]

        self._store.write_thread(category_id, meta)
        if writer.wrote_anything:
            self._store.compress_thread(category_id, info.id)
        return True

    def _needs_refetch(self, local: ThreadMeta, info: ThreadInfo, known: KnownHtml) -> bool:
        # TODO(original): edits of posts in a thread whose `last` did not change go unnoticed.
        if local.last != info.last or local.version < FORUM_THREAD_METADATA_VERSION:
            return True
        stored = len(local.all_posts())
        if stored != info.posts_num:
            self._count_mismatch(info, f"expected {info.posts_num} posts, stored {stored}")
            return True
        if len(known) != stored:
            self._count_mismatch(info, f"stored {stored} posts, but html of {len(known)}")
            return True
        return False

    def _count_mismatch(self, info: ThreadInfo, detail: str) -> None:
        log.warning("Post count mismatch in thread %s: %s", info.id, detail)
        self._reporter.error(ErrorKind.FORUM_COUNT_MISMATCH, str(info.id), detail)


class _PostWriter:
    """Stores the posts of one thread: their html and the metadata describing them."""

    def __init__(
        self,
        store: ForumStore,
        source: ForumSource,
        reporter: Reporter,
        category_id: int,
        thread_id: int,
        known: KnownHtml,
    ) -> None:
        self._store = store
        self._source = source
        self._reporter = reporter
        self._category_id = category_id
        self._thread_id = thread_id
        self._known = known
        self.wrote_anything = False

    def store(self, post: PostInfo, old_posts: dict[int, StoredPost]) -> StoredPost:
        old = old_posts.get(post.id)
        stored = StoredPost(
            id=post.id,
            title=post.title,
            poster=post.poster,
            stamp=post.stamp,
            last_edit=post.last_edit,
            last_edit_by=post.last_edit_by,
            revisions=list(old.revisions) if old else [],
        )
        have = self._known.get(post.id, set())
        fetched_revision = False
        if post.last_edit is not None:
            fetched_revision = self._store_revisions(post, stored, have)
        if fetched_revision or LATEST not in have:
            self._write(post.id, LATEST, post.content)
        stored.children = [self.store(child, old_posts) for child in post.children]
        return stored

    def _store_revisions(self, post: PostInfo, stored: StoredPost, have: set[str]) -> bool:
        """Download revisions we lack; returns whether any was downloaded."""
        fetched = False
        for revision in self._source.post_revisions(post.id):
            already = any(r.id == revision.id for r in stored.revisions)
            if already and str(revision.id) in have:
                continue
            body = self._fetch_revision(revision)
            if body is None:
                continue
            self._write(post.id, revision.id, body.content)
            stored.revisions = [r for r in stored.revisions if r.id != revision.id]
            stored.revisions.append(
                StoredPostRevision(body.title, revision.author, revision.id, revision.stamp)
            )
            fetched = True
        return fetched

    def _fetch_revision(self, revision: PostRevision) -> RevisionBody | None:
        try:
            return self._source.post_revision(revision.id)
        except HttpError as err:
            if err.status != 500:
                raise
            # Wikidot answers some old revisions with an internal error, forever.
            self._reporter.error(ErrorKind.WIKIDOT_INTERNAL, str(revision.id), str(err))
            return None

    def _write(self, post_id: int, revision: int | str, html: str) -> None:
        self._store.write_html(self._category_id, self._thread_id, post_id, revision, html)
        self.wrote_anything = True


def _category_meta(info: CategoryInfo, full_scan: bool, last_page: int) -> CategoryMeta:
    return CategoryMeta(
        id=info.id,
        title=info.title,
        description=info.description,
        threads=info.threads,
        posts=info.posts,
        last=info.last,
        last_user=info.last_user,
        full_scan=full_scan,
        last_page=last_page,
    )

