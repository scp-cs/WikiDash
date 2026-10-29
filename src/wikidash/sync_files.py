"""Page attachments: metadata, download and retry of failed downloads."""

import logging
import re
from typing import Protocol

from .api import TRANSIENT_ERRORS
from .models import FILE_METADATA_VERSION, FileMeta
from .paths import split_file_path
from .progress import ErrorKind, NullReporter, Reporter
from .workspace import Workspace

from .logging import create_logger

log = create_logger(__name__)

_LOCAL_FILE_URL = re.compile(r"/local--files/(.+)", re.IGNORECASE)


class FileSource(Protocol):
    def file_ids(self, page_id: int) -> list[int]: ...
    def file_info(self, file_id: int) -> FileMeta: ...
    def download(self, url: str) -> bytes: ...


def local_location(url: str) -> tuple[str, str] | None:
    """(page directory, file name) of a file hosted by wikidot; None for external URLs."""
    match = _LOCAL_FILE_URL.search(url)
    return split_file_path(match.group(1)) if match else None


class FileSyncer:
    def __init__(
        self, workspace: Workspace, source: FileSource, reporter: Reporter | None = None
    ) -> None:
        self._workspace = workspace
        self._source = source
        self._reporter = reporter or NullReporter()

    def sync_page_files(self, page_name: str, page_id: int, existing: list[FileMeta]) -> list[FileMeta]:
        """Bring a page's files up to date; returns the files it has now."""
        current: list[FileMeta] = []
        for meta in self._current_file_metas(page_name, page_id, existing):
            location = local_location(meta.url)
            if location is None:
                continue  # hosted elsewhere, not ours to archive
            page_dir, file_name = location
            current.append(meta)
            self._workspace.file_map[str(meta.file_id)] = {
                "url": meta.url,
                "path": f"{page_dir}/{file_name}",
            }
            self._download_if_missing(meta, page_dir)

        self._delete_removed(existing, current)
        return current

    def retry_pending(self) -> None:
        """Download files whose earlier download failed."""
        for file_id in self._workspace.pending_files.to_list():
            try:
                self._retry_one(int(file_id))
            except TRANSIENT_ERRORS as err:
                log.error("Pending file %s still failing: %s", file_id, err)
                self._reporter.error(ErrorKind.FILE_FETCH, str(file_id), str(err))

    # --- internals -----------------------------------------------------

    def _current_file_metas(
        self, page_name: str, page_id: int, existing: list[FileMeta]
    ) -> list[FileMeta]:
        known = {meta.file_id: meta for meta in existing}
        metas: list[FileMeta] = []
        for file_id in self._source.file_ids(page_id):
            cached = known.get(file_id)
            if cached is not None and cached.internal_version >= FILE_METADATA_VERSION:
                metas.append(cached)
                continue
            try:
                metas.append(self._source.file_info(file_id))
            except TRANSIENT_ERRORS as err:
                log.error("Could not read file %s of %s: %s", file_id, page_name, err)
                self._reporter.error(ErrorKind.FILE_META_FETCH, page_name, str(err))
        return metas

    def _download_if_missing(self, meta: FileMeta, page_dir: str) -> None:
        if self._workspace.file_is_complete(page_dir, meta.file_id, meta.size_bytes):
            return
        self._workspace.pending_files.add(meta.file_id)
        try:
            data = self._source.download(meta.url)
        except TRANSIENT_ERRORS as err:
            log.error("Unable to fetch %s: %s", meta.url, err)
            return  # stays pending
        self._workspace.write_file(page_dir, meta.file_id, data)
        self._workspace.pending_files.discard(meta.file_id)

    def _retry_one(self, file_id: int) -> None:
        mapped = self._workspace.file_map.get(str(file_id))
        url = mapped["url"] if mapped else self._source.file_info(file_id).url
        location = local_location(url)
        if location is None:
            self._workspace.pending_files.discard(file_id)
            return
        page_dir = location[0]
        if self._workspace.file_is_complete(page_dir, file_id, None):
            self._workspace.pending_files.discard(file_id)
            return
        self._workspace.write_file(page_dir, file_id, self._source.download(url))
        self._workspace.pending_files.discard(file_id)

    def _delete_removed(self, before: list[FileMeta], after: list[FileMeta]) -> None:
        still_there = {meta.file_id for meta in after}
        for meta in before:
            location = local_location(meta.url)
            if meta.file_id in still_there or location is None:
                continue
            log.info("File %s <%s> was removed from its page", meta.file_id, meta.url)
            self._workspace.file_path(location[0], meta.file_id).unlink(missing_ok=True)
