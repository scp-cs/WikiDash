"""One full backup run of a single wiki."""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from .ajax import WikidotAjax
from .api import WikidotApi
from .config import Config, WikiConfig
from .errors import WikidashError
from .forum_store import ForumStore
from .http import HttpClient
from .logging import create_logger
from .progress import Counters, ErrorKind, Status, StatusSink
from .ratelimit import RateLimiter
from .sitemap import SiteMap, fetch_sitemap, read_sitemap, removed_pages, write_sitemap
from .sync_files import FileSyncer
from .sync_forum import ForumSyncer
from .sync_pages import PageSyncer
from .sync_pending import retry_pending_revisions
from .userlist import UserList
from .workspace import Workspace

log = create_logger(__name__)

PAGE_WORKERS = 8
PROGRESS_INTERVAL_SECONDS = 10


class WikiRunner:
    """Archives one wiki: sitemap, pages, forum, then retries and compression."""

    def __init__(
        self,
        wiki: WikiConfig,
        config: Config,
        client: HttpClient,
        users: UserList,
        status: StatusSink,
    ) -> None:
        self._wiki = wiki
        self._config = config
        self._status = status
        self._client = client
        self._workspace = Workspace(config.base_directory / wiki.name)
        self._forum_store = ForumStore(config.base_directory / wiki.name)
        ajax = WikidotAjax(
            client, wiki.url, on_token_invalidated=lambda: status.error(ErrorKind.TOKEN_INVALIDATED)
        )
        self._api = WikidotApi(client, ajax, wiki.url, on_user=users.register)
        self._counters = Counters()
        self._files = FileSyncer(self._workspace, self._api, status)

    def run(self) -> None:
        self._status.handshake()
        try:
            self._run_phases()
        except Exception as err:
            self._status.progress(Status.FATAL_ERROR)
            log.exception("[%s] run failed", self._wiki.name)
            raise WikidashError(f"{self._wiki.name}: {err}") from err
        finally:
            self._workspace.save()
        self._status.finish()

    def _run_phases(self) -> None:
        name = self._wiki.name
        self._status.progress(Status.BUILDING_SITEMAP)
        sitemap = fetch_sitemap(self._client, self._wiki.url, self._config.blacklist)
        self._status.preflight(len(sitemap))
        previous = read_sitemap(self._workspace.meta / "sitemap.json")
        self._forget_removed_pages(previous, sitemap)

        self._status.progress(Status.PAGES_MAIN, done=0, postponed=0)
        self._sync_pages(sitemap, previous)
        write_sitemap(self._workspace.meta / "sitemap.json", sitemap)  # marks pages as done

        self._status.progress(Status.FORUMS_MAIN)
        ForumSyncer(self._forum_store, self._api, self._status).sync_all()

        self._status.progress(Status.FILES_PENDING)
        self._files.retry_pending()
        self._status.progress(Status.PAGES_PENDING)
        retry_pending_revisions(self._workspace, self._api, self._status)

        self._status.progress(Status.COMPRESSING)
        self._workspace.compress_all_revisions()
        self._forum_store.compress_all()
        log.info("[%s] done", name)

    def _forget_removed_pages(self, previous: SiteMap | None, current: SiteMap) -> None:
        if previous is None:
            log.info("[%s] no previous sitemap, doing a full scan", self._wiki.name)
            return
        for name in removed_pages(previous, current):
            log.info("[%s] page %s was removed", self._wiki.name, name)
            meta = self._workspace.read_page_meta(name)
            self._workspace.remove_page(name)
            if meta is not None:
                self._workspace.page_id_map.pop(str(meta.page_id))

    def _sync_pages(self, sitemap: SiteMap, previous: SiteMap | None) -> None:
        syncer = PageSyncer(self._workspace, self._api, self._files, self._counters, self._status)
        stop = threading.Event()
        reporter = threading.Thread(
            target=self._report_progress, args=(stop, len(sitemap)), daemon=True
        )
        reporter.start()
        try:
            with ThreadPoolExecutor(max_workers=PAGE_WORKERS) as pool:
                for name, last_modified in sitemap.items():
                    pool.submit(self._sync_one, syncer, name, last_modified, previous)
        finally:
            stop.set()
            reporter.join()
        self._status.progress(
            Status.PAGES_MAIN, done=self._counters.done, postponed=self._counters.postponed
        )

    def _sync_one(
        self, syncer: PageSyncer, name: str, last_modified: int | None, previous: SiteMap | None
    ) -> None:
        if self._config.delay_ms:
            time.sleep(self._config.delay_ms / 1000)
        try:
            syncer.sync_page(name, last_modified, previous)
        except Exception:
            # An unexpected bug on one page must not stop the whole backup.
            log.exception("[%s] page %s failed unexpectedly", self._wiki.name, name)
            self._workspace.pending_pages.add(name)
            self._counters.page_postponed()

    def _report_progress(self, stop: threading.Event, total: int) -> None:
        while not stop.wait(PROGRESS_INTERVAL_SECONDS):
            self._workspace.save()
            log.info("[%s] %s/%s pages", self._wiki.name, self._counters.done, total)
            self._status.progress(
                Status.PAGES_MAIN, done=self._counters.done, postponed=self._counters.postponed
            )


def run_all(
    config: Config,
    make_runner: Callable[[WikiConfig], WikiRunner],
) -> list[str]:
    """Run every configured wiki, a few at a time. Returns the names of failed wikis."""
    failed: list[str] = []

    def run(wiki: WikiConfig) -> None:
        try:
            make_runner(wiki).run()
        except WikidashError as err:
            log.error("%s", err)
            failed.append(wiki.name)

    with ThreadPoolExecutor(max_workers=config.parallel_wikis) as pool:
        list(pool.map(run, config.wikis))
    return failed


def make_client(config: Config) -> HttpClient:
    limiter = (
        RateLimiter(config.ratelimit.bucket_size, config.ratelimit.refill_seconds)
        if config.ratelimit
        else None
    )
    return HttpClient(
        limiter=limiter, http_proxy=config.http_proxy, socks_proxy=config.socks_proxy
    )
