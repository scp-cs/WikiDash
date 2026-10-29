"""In-memory stand-in for WikidotApi, used by the sync tests."""

from wikidash.errors import WikidashError
from wikidash.models import FileMeta, PageInfo, PageRevision, UserId


class FakePage:
    def __init__(
        self,
        page_id: int,
        revisions: int = 3,
        files: dict[int, bytes] | None = None,
        title: str = "Title",
    ) -> None:
        self.page_id = page_id
        self.revision_count = revisions
        self.files = files or {}
        self.title = title
        self.locked = False


class FakeWikidot:
    def __init__(self) -> None:
        self.pages: dict[str, FakePage] = {}
        self.failing_revisions: set[int] = set()
        self.unreachable_pages: set[str] = set()
        self.calls: list[str] = []

    def add_page(self, name: str, page: FakePage) -> None:
        self.pages[name] = page

    # --- PageSource ----------------------------------------------------

    def page_info(self, page_name: str) -> PageInfo:
        self.calls.append(f"page_info:{page_name}")
        if page_name in self.unreachable_pages:
            raise WikidashError("unreachable")
        page = self.pages[page_name]
        return PageInfo(page_id=page.page_id, title=page.title, rating=5, tags=["tag"], parent=None)

    def revisions(self, page_id: int, *, newer_than: int | None = None) -> list[PageRevision]:
        self.calls.append(f"revisions:{page_id}:{newer_than}")
        page = next(p for p in self.pages.values() if p.page_id == page_id)
        numbers = range(page.revision_count - 1, -1, -1)
        return [
            PageRevision(n, page_id * 100 + n, author=1, stamp=n, flags="S")
            for n in numbers
            if newer_than is None or n > newer_than
        ]

    def revision_source(self, global_revision: int) -> str:
        self.calls.append(f"source:{global_revision}")
        if global_revision in self.failing_revisions:
            raise WikidashError("boom")
        return f"source {global_revision}"

    def voters(self, page_id: int) -> list[tuple[UserId, bool]] | None:
        return [(1, True)]

    def is_page_locked(self, page_id: int) -> bool:
        return next(p for p in self.pages.values() if p.page_id == page_id).locked

    # --- FileSource ----------------------------------------------------

    def file_ids(self, page_id: int) -> list[int]:
        return list(next(p for p in self.pages.values() if p.page_id == page_id).files)

    def file_info(self, file_id: int) -> FileMeta:
        self.calls.append(f"file_info:{file_id}")
        data = next(p.files[file_id] for p in self.pages.values() if file_id in p.files)
        return FileMeta(
            file_id=file_id,
            name=f"f{file_id}.bin",
            url=f"http://t.wikidot.com/local--files/some:page/f{file_id}.bin",
            size=f"{len(data)} bytes",
            size_bytes=len(data),
            mime="application/octet-stream",
            content="data",
            author=1,
            stamp=1,
        )

    def download(self, url: str) -> bytes:
        self.calls.append(f"download:{url}")
        file_id = int(url.rsplit("/f", 1)[1].split(".")[0])
        return next(p.files[file_id] for p in self.pages.values() if file_id in p.files)
