"""In-memory stand-in for the forum part of WikidotApi."""

from wikidash.errors import HttpError, WikidashError
from wikidash.forum_models import CategoryInfo, PostInfo, PostRevision, RevisionBody, ThreadInfo


class FakeForum:
    def __init__(self) -> None:
        self.categories: dict[int, CategoryInfo] = {}
        self.threads: dict[int, list[ThreadInfo]] = {}  # category -> threads
        self.posts: dict[int, list[PostInfo]] = {}  # thread -> top-level posts
        self.revisions: dict[int, list[PostRevision]] = {}  # post -> revisions
        self.failing_threads: set[int] = set()
        self.internal_error_revisions: set[int] = set()
        self.page_size = 2
        self.calls: list[str] = []

    def forum_categories(self) -> list[CategoryInfo]:
        return list(self.categories.values())

    def thread_page(self, category_id: int, page: int) -> list[ThreadInfo]:
        start = (page - 1) * self.page_size
        return self.threads[category_id][start : start + self.page_size]

    def is_thread_locked(self, thread_id: int) -> bool:
        return False

    def thread_posts(self, thread_id: int) -> list[PostInfo]:
        self.calls.append(f"posts:{thread_id}")
        if thread_id in self.failing_threads:
            raise WikidashError("down")
        return self.posts[thread_id]

    def post_revisions(self, post_id: int) -> list[PostRevision]:
        return self.revisions[post_id]

    def post_revision(self, revision_id: int) -> RevisionBody:
        self.calls.append(f"revision:{revision_id}")
        if revision_id in self.internal_error_revisions:
            raise HttpError(500, "x")
        return RevisionBody(title=f"title {revision_id}", content=f"<p>rev {revision_id}</p>")
