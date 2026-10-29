"""On-disk layout of one wiki's archive (compatible with the original WikiComma).

    meta/sitemap.json              page name -> last modification (ms)
    meta/pages/<name>.json         PageMeta
    meta/page_id_map.json          page id -> page name
    meta/file_map.json             file id -> {url, path}
    meta/pending_*.json            work postponed to the next run
    pages/<name>/<rev>.txt         page source (loose, until compressed)
    pages/<name>.7z                compressed revisions, members '<rev>.txt'
    files/<page>/<file id>         downloaded attachments
    forum/...                      see forum_store.py
"""

import shutil
from pathlib import Path

from peewee import Database

from .archive7z import Archive7z
from .logging import create_logger
from .models import PageMeta
from .paths import normalize_page_name, reencode_component
from .store import PersistentDict, PersistentSet, read_json, write_json

log = create_logger(__name__)


class Workspace:
    def __init__(self, root: Path, database: Database | None = None) -> None:
        self.root = root
        self.meta = root / "meta"
        self.page_id_map = PersistentDict(self.meta / "page_id_map.json")
        self.file_map = PersistentDict(self.meta / "file_map.json")
        self.pending_files = PersistentSet(self.meta / "pending_files.json")
        self.pending_pages = PersistentSet(self.meta / "pending_pages.json")
        # global revision id -> page id
        self.pending_revisions = PersistentDict(self.meta / "pending_revisions.json")
        self._database = database

    def save(self) -> None:
        """Flush every persistent collection that changed."""
        for store in (
            self.page_id_map,
            self.file_map,
            self.pending_files,
            self.pending_pages,
            self.pending_revisions,
        ):
            store.save()

    # --- page metadata -------------------------------------------------

    def page_meta_path(self, page: str) -> Path:
        return self.meta / "pages" / f"{normalize_page_name(page)}.json"

    def page_meta_exists(self, page: str) -> bool:
        return self.page_meta_path(page).is_file()

    def read_page_meta(self, page: str) -> PageMeta | None:
        """Stored metadata, or None if missing or unreadable (then it is fetched again)."""
        path = self.page_meta_path(page)
        if not path.exists():
            return None
        try:
            return PageMeta.from_dict(read_json(path))
        except (KeyError, TypeError, ValueError):
            log.warning("Unreadable page metadata %s, will refetch", path)
            return None

    def write_page_meta(self, page: str, meta: PageMeta) -> None:
        write_json(self.page_meta_path(page), meta.to_dict())

    def remove_page(self, page: str) -> None:
        """Forget everything stored for a deleted or replaced page."""
        self.page_meta_path(page).unlink(missing_ok=True)
        self.revision_archive(page).path.unlink(missing_ok=True)
        shutil.rmtree(self._loose_dir(page), ignore_errors=True)
        shutil.rmtree(self.files_dir(page), ignore_errors=True)

    # --- revisions -----------------------------------------------------

    def revision_archive(self, page: str) -> Archive7z:
        return Archive7z(self.root / "pages" / f"{normalize_page_name(page)}.7z")

    def _loose_dir(self, page: str) -> Path:
        return self.root / "pages" / normalize_page_name(page)

    def local_revisions(self, page: str) -> set[int]:
        """Revision numbers whose source we already have, loose or archived."""
        names = list(self.revision_archive(page).names())
        if self._loose_dir(page).is_dir():
            names.extend(p.name for p in self._loose_dir(page).iterdir())
        return {int(n.removesuffix(".txt")) for n in names if n.endswith(".txt") and n[:-4].isdigit()}

    def write_revision(self, page: str, revision: int, text: str) -> None:
        directory = self._loose_dir(page)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{revision}.txt").write_text(text, encoding="utf-8")

    def compress_revisions(self, page: str) -> None:
        """Move loose revision files of a page into its .7z archive."""
        directory = self._loose_dir(page)
        if not directory.is_dir():
            return
        loose = [p for p in directory.iterdir() if p.is_file() and p.name[:-4].isdigit()]
        loose = [p for p in loose if p.suffix == ".txt"]
        if loose:
            self.revision_archive(page).add({p.name: p.read_bytes() for p in loose})
            for path in loose:
                path.unlink()
        if not any(directory.iterdir()):
            directory.rmdir()

    def compress_all_revisions(self) -> None:
        """Compress every page directory left loose (e.g. by an interrupted run)."""
        pages = self.root / "pages"
        if not pages.is_dir():
            return
        for entry in pages.iterdir():
            if entry.is_dir() and not entry.name.startswith("."):
                self.compress_revisions(entry.name)

    # --- files ---------------------------------------------------------

    def files_dir(self, page: str) -> Path:
        return self.root / "files" / reencode_component(page)

    def file_path(self, page_dir: str, file_id: int) -> Path:
        return self.root / "files" / page_dir / str(file_id)

    def file_is_complete(self, page_dir: str, file_id: int, expected_size: int | None) -> bool:
        path = self.file_path(page_dir, file_id)
        return path.is_file() and (expected_size is None or path.stat().st_size == expected_size)

    def write_file(self, page_dir: str, file_id: int, data: bytes) -> None:
        path = self.file_path(page_dir, file_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)
