"""Incremental sync of one page: metadata, files and revision sources."""

from collections.abc import Callable
from typing import Any, Protocol

from .api import TRANSIENT_ERRORS
from .logging import create_logger
from .models import PAGE_METADATA_VERSION, PageInfo, PageMeta, PageRevision, UserId
from .progress import Counters, ErrorKind, NullReporter, Reporter
from .sitemap import SiteMap
from .sync_files import FileSyncer
from .workspace import Workspace

log = create_logger(__name__)

# Old archives use this page id for pages whose id could not be determined.
UNKNOWN_PAGE_ID = -1


class PageSource(Protocol):
    def page_info(self, page_name: str) -> PageInfo: ...
    def revisions(self, page_id: int, *, newer_than: int | None = None) -> list[PageRevision]: ...
    def revision_source(self, global_revision: int) -> str: ...
    def voters(self, page_id: int) -> list[tuple[UserId, bool]] | None: ...
    def is_page_locked(self, page_id: int) -> bool: ...


class PageSyncer:
    def __init__(
        self,
        workspace: Workspace,
        source: PageSource,
        files: FileSyncer,
        counters: Counters,
        reporter: Reporter | None = None,
    ) -> None:
        self._workspace = workspace
        self._source = source
        self._files = files
        self._counters = counters
        self._reporter = reporter or NullReporter()

    def sync_page(self, name: str, last_modified: int | None, previous: SiteMap | None) -> None:
        """Make the local copy of `name` current. Failures postpone the page, never raise."""
        if self._unchanged_since_last_run(name, last_modified, previous):
            self._counters.page_done()
            return

        meta = self._workspace.read_page_meta(name)
        if _needs_refresh(meta, last_modified):
            try:
                meta = self._refresh(name, last_modified, meta)
            except TRANSIENT_ERRORS as err:
                log.error("Postponing page %s: %s", name, err)
                self._postpone(name)
                return

        if meta is None or meta.page_id == UNKNOWN_PAGE_ID:
            self._postpone(name)
            return

        self._fetch_missing_revisions(name, meta)
        self._workspace.pending_pages.discard(name)
        self._counters.page_done()

    # --- deciding what to do -------------------------------------------

    def _unchanged_since_last_run(
        self, name: str, last_modified: int | None, previous: SiteMap | None
    ) -> bool:
        # The sitemap is only written once a run has saved everything, so a page
        # with the same date and stored metadata is fully done.
        return (
            previous is not None
            and name in previous
            and previous[name] == last_modified
            and self._workspace.page_meta_exists(name)
        )

    def _postpone(self, name: str) -> None:
        self._workspace.pending_pages.add(name)
        self._counters.page_postponed()

    # --- metadata ------------------------------------------------------

    def _refresh(self, name: str, last_modified: int | None, old: PageMeta | None) -> PageMeta | None:
        info = self._source.page_info(name)
        if info.page_id is None:
            return old

        meta = self._start_from(name, info, old)
        self._workspace.page_id_map[str(meta.page_id)] = name
        meta.rating = info.rating
        meta.forum_thread = info.forum_thread
        meta.tags = info.tags or None
        meta.title = info.title
        meta.sitemap_update = last_modified

        meta.votings = self._try(ErrorKind.VOTE_FETCH, name, meta.votings, self._source.voters, meta.page_id)
        meta.is_locked = self._try(
            ErrorKind.LOCK_STATUS_FETCH, name, meta.is_locked, self._source.is_page_locked, meta.page_id
        )
        meta.files = self._try(
            ErrorKind.FILE_FETCH, name, meta.files, self._files.sync_page_files, name, meta.page_id, meta.files
        )

        newest = max((r.revision for r in meta.revisions), default=None)
        meta.revisions = self._source.revisions(meta.page_id, newer_than=newest) + meta.revisions
        self._workspace.write_page_meta(name, meta)
        return meta

    def _start_from(self, name: str, info: PageInfo, old: PageMeta | None) -> PageMeta:
        """Metadata to build upon: the old one, or a blank one if the page was recreated."""
        assert info.page_id is not None
        replaced = old is not None and old.page_id not in (UNKNOWN_PAGE_ID, info.page_id)
        if old is None or replaced:
            if old is not None:
                log.info("Page %s got replaced", name)
                self._workspace.remove_page(name)
                self._workspace.page_id_map.pop(str(old.page_id))
            return PageMeta(name=name, page_id=info.page_id, parent=info.parent)
        return PageMeta(
            name=name,
            page_id=old.page_id,
            revisions=old.revisions,
            files=old.files,
            votings=old.votings,
            is_locked=old.is_locked,
            parent=info.parent,
        )

    def _try[T](
        self, kind: ErrorKind, name: str, fallback: T, func: Callable[..., T | None], *args: Any
    ) -> T:
        """Run an optional step; on failure report it and keep the old value."""
        try:
            result = func(*args)
        except TRANSIENT_ERRORS as err:
            log.error("%s of %s failed: %s", kind.name, name, err)
            self._reporter.error(kind, name, str(err))
            return fallback
        return fallback if result is None else result

    # --- revision sources ----------------------------------------------

    def _fetch_missing_revisions(self, name: str, meta: PageMeta) -> None:
        have = self._workspace.local_revisions(name)
        fetched_any = False
        for revision in meta.revisions:
            if revision.revision in have:
                continue
            try:
                text = self._source.revision_source(revision.global_revision)
            except TRANSIENT_ERRORS as err:
                log.error("Postponing revision %s of %s: %s", revision.global_revision, name, err)
                self._workspace.pending_revisions[str(revision.global_revision)] = meta.page_id
                self._counters.page_postponed()
                continue
            self._workspace.write_revision(name, revision.revision, text)
            self._workspace.pending_revisions.pop(str(revision.global_revision))
            fetched_any = True
        if fetched_any:
            self._workspace.compress_revisions(name)


def _needs_refresh(meta: PageMeta | None, last_modified: int | None) -> bool:
    return (
        meta is None
        or last_modified is None  # no date from wikidot: always check
        or meta.sitemap_update != last_modified
        or meta.version < PAGE_METADATA_VERSION
    )
