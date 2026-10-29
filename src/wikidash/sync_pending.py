"""Retrying work that failed in earlier runs: page revision sources."""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from .api import TRANSIENT_ERRORS
from .progress import ErrorKind, NullReporter, Reporter
from .workspace import Workspace

from .logging import create_logger

log = create_logger(__name__)

# System pages that are huge and unimportant: give up on a failing revision at once.
GIVE_UP_PREFIXES = ("nav:", "tech:")
WORKERS = 6


class RevisionSource(Protocol):
    def revision_source(self, global_revision: int) -> str: ...


def retry_pending_revisions(
    workspace: Workspace,
    source: RevisionSource,
    reporter: Reporter | None = None,
    workers: int = WORKERS,
) -> None:
    reporter = reporter or NullReporter()
    page_names = {int(page_id): name for page_id, name in workspace.page_id_map.items()}

    def retry_one(item: tuple[str, int]) -> None:
        global_revision, page_id = int(item[0]), item[1]
        name = page_names.get(page_id)
        meta = workspace.read_page_meta(name) if name else None
        if name is None or meta is None or meta.page_id != page_id:
            _give_up(workspace, reporter, global_revision, "Unknown Page", f"page id {page_id}")
            return
        revision = next((r for r in meta.revisions if r.global_revision == global_revision), None)
        if revision is None:
            _give_up(workspace, reporter, global_revision, name, "revision not in page metadata")
            return
        try:
            text = source.revision_source(global_revision)
        except TRANSIENT_ERRORS as err:
            if name.startswith(GIVE_UP_PREFIXES):
                _give_up(workspace, reporter, global_revision, name, str(err))
            else:
                log.error("Revision %s of %s still failing: %s", global_revision, name, err)
            return
        workspace.write_revision(name, revision.revision, text)
        workspace.pending_revisions.pop(str(global_revision))

    items = [(key, int(page_id)) for key, page_id in workspace.pending_revisions.items()]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(retry_one, items))


def _give_up(
    workspace: Workspace, reporter: Reporter, global_revision: int, name: str, why: str
) -> None:
    log.error("Giving up on revision %s of %s: %s", global_revision, name, why)
    reporter.error(ErrorKind.GIVING_UP, name, why)
    workspace.pending_revisions.pop(str(global_revision))
