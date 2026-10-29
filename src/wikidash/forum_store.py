"""On-disk layout of the forum (compatible with the original WikiComma).

    meta/forum/category/<category>.json      CategoryMeta
    meta/forum/<category>/<thread>.json      ThreadMeta
    forum/<category>/<thread>/<post>/<revision id | latest>.html   (loose, until compressed)
    forum/<category>/<thread>.7z             the same files, members '<post>/<revision>.html'
"""

import logging
import shutil
from pathlib import Path

from .archive7z import Archive7z
from .forum_models import CategoryMeta, ThreadMeta
from .store import read_json, write_json

log = logging.getLogger(__name__)

LATEST = "latest"
# post id -> names of stored revisions ('latest' or a revision id)
KnownHtml = dict[int, set[str]]


class ForumStore:
    def __init__(self, root: Path) -> None:
        self._meta = root / "meta" / "forum"
        self._forum = root / "forum"

    # --- metadata ------------------------------------------------------

    def read_category(self, category_id: int) -> CategoryMeta | None:
        path = self._meta / "category" / f"{category_id}.json"
        return CategoryMeta.from_dict(read_json(path)) if path.exists() else None

    def write_category(self, meta: CategoryMeta) -> None:
        write_json(self._meta / "category" / f"{meta.id}.json", meta.to_dict())

    def read_thread(self, category_id: int, thread_id: int) -> ThreadMeta | None:
        path = self._thread_meta_path(category_id, thread_id)
        return ThreadMeta.from_dict(read_json(path)) if path.exists() else None

    def write_thread(self, category_id: int, meta: ThreadMeta) -> None:
        write_json(self._thread_meta_path(category_id, meta.id), meta.to_dict())

    def _thread_meta_path(self, category_id: int, thread_id: int) -> Path:
        return self._meta / str(category_id) / f"{thread_id}.json"

    # --- post html -----------------------------------------------------

    def known_html(self, category_id: int, thread_id: int) -> KnownHtml:
        """Which revisions of which posts are stored, loose or archived."""
        names = self._archive(category_id, thread_id).names()
        loose = self._loose_dir(category_id, thread_id)
        if loose.is_dir():
            names.extend(f"{p.parent.name}/{p.name}" for p in loose.glob("*/*.html"))

        known: KnownHtml = {}
        for name in names:
            post, _, revision = name.removesuffix(".html").partition("/")
            if post.isdigit() and revision:
                known.setdefault(int(post), set()).add(revision)
        return known

    def write_html(
        self, category_id: int, thread_id: int, post_id: int, revision: int | str, html: str
    ) -> None:
        directory = self._loose_dir(category_id, thread_id) / str(post_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{revision}.html").write_text(html, encoding="utf-8")

    def compress_thread(self, category_id: int, thread_id: int) -> None:
        """Move a thread's loose html into its .7z archive."""
        loose = self._loose_dir(category_id, thread_id)
        if not loose.is_dir():
            return
        files = {
            f"{path.parent.name}/{path.name}": path.read_bytes() for path in loose.glob("*/*.html")
        }
        unexpected = [p for p in loose.rglob("*") if p.is_file() and p.suffix != ".html"]
        if unexpected:
            log.error("Not compressing thread %s: unexpected file %s", thread_id, unexpected[0])
            return
        if files:
            self._archive(category_id, thread_id).add(files)
        shutil.rmtree(loose)

    def compress_all(self) -> None:
        """Compress every thread directory left loose (e.g. by an interrupted run)."""
        if not self._forum.is_dir():
            return
        for category in self._forum.iterdir():
            if not category.is_dir() or category.name.startswith("."):
                continue
            for thread in category.iterdir():
                if thread.is_dir() and category.name.isdigit() and thread.name.isdigit():
                    self.compress_thread(int(category.name), int(thread.name))

    def _archive(self, category_id: int, thread_id: int) -> Archive7z:
        return Archive7z(self._forum / str(category_id) / f"{thread_id}.7z")

    def _loose_dir(self, category_id: int, thread_id: int) -> Path:
        return self._forum / str(category_id) / str(thread_id)
