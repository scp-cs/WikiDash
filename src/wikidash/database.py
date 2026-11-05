import logging
from collections import defaultdict
from datetime import datetime

from peewee import Database

from .models.forum_models import CategoryMeta, StoredPost, StoredPostRevision, ThreadMeta
from .models.page_models import FileMeta, PageMeta, PageRevision
from .models.sqlite_models import (
    FileModel,
    ForumCategoryModel,
    ForumPostModel,
    ForumPostRevisionModel,
    ForumThreadModel,
    PageHasTag,
    PageHasUserVote,
    PageModel,
    PageRevisionModel,
    PageTagModel,
    UserModel,
)
from .models.user_models import User

ALL_MODELS = [
    UserModel,
    PageModel,
    PageTagModel,
    PageRevisionModel,
    PageHasTag,
    PageHasUserVote,
    ForumCategoryModel,
    ForumPostModel,
    ForumThreadModel,
    ForumPostRevisionModel,
    FileModel,
]

log = logging.getLogger(__name__)


def create_tables(database: Database) -> None:
    database.create_tables(ALL_MODELS)


def bind_tables(database: Database) -> None:
    database.bind(ALL_MODELS)

# TODO: Models are bound to the database in `cli.py` and the RecordSink class really has no control over the SQLite setup
# This is not really a problem but kind of a shitty abstraction

# TODO: Figure out the logic for updating this incrementally without reinserting everything every time

class DatabaseRecordSink:
    """
    Keeps data to be stored as database records. Objects are queued for a database write
    and only flushed when a site runner finishes to keep database integrity.
    """

    # Save order:
    # 1. Users
    # 2. Files
    # 3. Forum categories
    # 4. Forum threads
    # 5. Forum posts
    # 6. Forum post revisions
    # 7. (Page => PageTags => PageVotes => PageRevisions) for each page

    def __init__(self) -> None:
        self._pages: set[PageMeta] = set()
        self._revisions: defaultdict[int, set[PageRevision]] = defaultdict(set[PageRevision])
        self._users: set[User] = set()
        self._categories: set[CategoryMeta] = set()
        self._forum_posts: defaultdict[int, set[StoredPost]] = defaultdict(set[StoredPost])
        self._forum_threads: defaultdict[int, set[ThreadMeta]] = defaultdict(set[ThreadMeta])
        self._forum_revisions: defaultdict[int, set[StoredPostRevision]] = defaultdict(set[StoredPostRevision])
        self._files: set[FileMeta] = set()

    def queue_page(self, page: PageMeta) -> None:
        self._pages.add(page)

    def queue_revision(self, rev: PageRevision, page: PageMeta) -> None:
        self._revisions[page.page_id].add(rev)

    def queue_user(self, user: User) -> None:
        self._users.add(user)

    def queue_forum_category(self, category: CategoryMeta) -> None:
        self._categories.add(category)

    def queue_forum_post(self, post: StoredPost, thread: ThreadMeta) -> None:
        self._forum_posts[thread.id].add(post)

    def queue_forum_thread(self, thread: ThreadMeta, category: CategoryMeta) -> None:
        self._forum_threads[category.id].add(thread)

    def queue_forum_revision(self, revision: StoredPostRevision, post: StoredPost) -> None:
        self._forum_revisions[post.id].add(revision)

    def queue_file(self, file: FileMeta) -> None:
        self._files.add(file)

    def _save_user(self, user: User) -> None:
        UserModel.insert(
            wikidot_id=user.user_id,
            username=user.username,
            user_since=datetime.fromtimestamp(user.wikidot_user_since),
            fetched_at=datetime.fromtimestamp(user.fetched_at / 1000),
            activity=user.activity,
            real_name=user.real_name,
            gender=user.gender,
            birthday=datetime.fromtimestamp(user.birthday / 1000) if user.birthday else None,
            location=user.location,
            website=user.website,
            bio=user.bio,
            account_type=user.account_type,
        ).execute()

        self._users.remove(user)

    def _save_page_revision(self, revision: PageRevision, page: PageMeta) -> None:

        PageRevisionModel.insert(
            revision_id=revision.revision,
            global_id=revision.global_revision,
            author=UserModel.get_or_none(UserModel.wikidot_id == revision.author),
            timestamp=datetime.fromtimestamp(revision.stamp or 0),
            flags=revision.flags,
            comment=revision.commentary,
            page=PageModel.get_or_none(PageModel.wikidot_id == page.page_id),
        ).returning(PageRevisionModel).execute()

    def _save_page(self, page: PageMeta) -> None:

        if page.parent is not None and PageModel.get_or_none(PageModel.name == page.parent) is None:
            return

        # TODO: The forum thread

        newpage = (
            PageModel.insert(
                wikidot_id=page.page_id,
                name=page.name,
                title=page.title,
                sitemap_update=datetime.fromtimestamp(page.sitemap_update / 1000)
                if page.sitemap_update
                else None,
                version=page.version,
                parent=PageModel.get_or_none(PageModel.name == page.parent),
                rating=page.rating,
            )
            .returning(PageModel)
            .execute()
        )

        for tag in page.tags or []:
            tag_model: PageTagModel = PageTagModel.get_or_create(text=tag)  # type: ignore[no-untyped-call]
            PageHasTag.create(page=newpage, tag=tag_model)

        for user_id, vote in page.votings or []:
            if user_id:
                user = UserModel.get_or_none(UserModel.wikidot_id == user_id)
                PageHasUserVote.create(page=newpage, user=user, vote=vote)
            else:
                PageHasUserVote.create(page=newpage, vote=vote, user_unknown=True)

        self._pages.remove(page)

    def _save_file(self, file: FileMeta) -> None:
        FileModel.insert(
            wikidot_id = file.file_id,
            name = file.name,
            url = file.url,
            size_text = file.size,
            size_bytes = file.size_bytes,
            mime_type = file.mime,
            description = file.content,
            author = UserModel.get_or_none(UserModel.wikidot_id == file.author),
            upload_time = datetime.fromtimestamp(file.stamp) if file.stamp else None
        ).returning(FileModel).execute()

    def _save_forum_category(self, category: CategoryMeta) -> None:
        ForumCategoryModel.insert(
            wikidot_id = category.id,
            title = category.title,
            description = category.description,
            thread_count = category.threads,
            post_count = category.posts,
            # TODO: These are probably redundant, you can do that with a SELECT after, just like some others
            last_activity = datetime.fromtimestamp(category.last) if category.last else None,
            last_author = UserModel.get_or_none(UserModel.wikidot_id == category.last_user) if category.last_user else None
        )

    def _save_forum_post(self, post: StoredPost, thread: ThreadMeta) -> None:
        ...

    def _save_forum_post_revision(self, revision: ForumPostRevisionModel, post: StoredPost) -> None:
        ...

    def flush(self) -> None:

        def save_all() -> None:
            for user in self._users:
                self._save_user(user)