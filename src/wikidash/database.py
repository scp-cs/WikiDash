import logging
from datetime import datetime

from peewee import Database

from .forum_models import CategoryMeta, StoredPost, StoredPostRevision, ThreadMeta
from .models import FileMeta, PageMeta, PageRevision
from .sqlite_models import (
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
from .user_models import User

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


class DatabaseRecordSink:
    """
    Keeps data to be stored as database records. Objects are queued for a database write
    and only flushed when a site runner finishes to keep database integrity.
    """

    def __init__(self) -> None:
        self._pages: set[PageMeta] = set()
        self._revisions: set[PageRevision] = set()
        self._users: set[User] = set()
        self._categories: set[CategoryMeta] = set()
        self._forum_posts: set[StoredPost] = set()
        self._forum_threads: set[ThreadMeta] = set()
        self._forum_revisions: set[StoredPostRevision] = set()
        self._files: set[FileMeta] = set()

    def queue_page(self, page: PageMeta) -> None:
        self._pages.add(page)

    def queue_revision(self, rev: PageRevision) -> None:
        self._revisions.add(rev)

    def queue_user(self, user: User) -> None:
        self._users.add(user)

    def queue_forum_category(self, category: CategoryMeta) -> None:
        self._categories.add(category)

    def queue_forum_post(self, post: StoredPost) -> None:
        self._forum_posts.add(post)

    def queue_forum_revision(self, revision: StoredPostRevision) -> None:
        self._forum_revisions.add(revision)

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

        self._revisions.remove(revision)

    def _save_page(self, page: PageMeta) -> None:

        if page.parent is not None and PageModel.get_or_none(PageModel.name == page.parent) is None:
            return

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
