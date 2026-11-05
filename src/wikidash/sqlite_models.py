from peewee import (
    AutoField,
    BooleanField,
    CharField,
    DateTimeField,
    ForeignKeyField,
    IntegerField,
    Model,
    TextField,
    TimestampField,
)
from playhouse.shortcuts import ThreadSafeDatabaseMetadata

# TODO: Probably add file paths?


class ModelBase(Model):
    class Meta:
        model_metadata_class = ThreadSafeDatabaseMetadata


class UserModel(ModelBase):
    id = AutoField()
    wikidot_id = IntegerField(unique=True)
    username = CharField(512, unique=True)
    user_since = DateTimeField()
    fetched_at = TimestampField()
    activity = IntegerField()
    real_name = TextField(null=True, default=None)
    gender = TextField(null=True, default=None)
    birthday = DateTimeField(null=True, default=None)
    location = TextField(null=True, default=None)
    website = TextField(null=True, default=None)
    bio = TextField(null=True, default=None)
    account_type = TextField(null=True, default=None)

    class Meta:
        table_name = "user"


class PageTagModel(ModelBase):
    id = AutoField()
    text = TextField()

    class Meta:
        table_name = "page_tag"


class ForumCategoryModel(ModelBase):
    id = AutoField()
    wikidot_id = IntegerField(unique=True)
    title = TextField()
    description = TextField()
    thread_count = IntegerField()
    post_count = IntegerField()
    last_activity = TimestampField(null=True, default=None)
    last_author = ForeignKeyField(UserModel, null=True, default=None)

    class Meta:
        table_name = "forum_category"


class ForumThreadModel(ModelBase):
    id = AutoField(unique=True)
    wikidot_id = IntegerField(unique=True)
    title = TextField()
    description = TextField()
    post_count = IntegerField()
    sticky = BooleanField(default=False)
    started = DateTimeField()
    started_by = ForeignKeyField(UserModel, backref="forum_threads")
    last_post = TimestampField(null=True, default=None)
    last_post_author = ForeignKeyField(UserModel, backref="last_posts", null=True, default=None)
    locked = BooleanField(default=False)
    category = ForeignKeyField(ForumCategoryModel, null=True, default=None, backref="threads")

    class Meta:
        table_name = "forum_thread"


class PageModel(ModelBase):
    id = AutoField(unique=True)
    name = TextField(unique=True)
    wikidot_id = IntegerField(unique=True)
    title = TextField(null=True, default=None)
    sitemap_update = DateTimeField(null=True, default=None)
    version = IntegerField(default=0)
    parent = ForeignKeyField("self", null=True, default=None, backref="children")
    rating = IntegerField(default=0)
    forum_thread = ForeignKeyField(ForumThreadModel, null=True, default=None, backref="page")
    locked = BooleanField(null=True, default=None)

    class Meta:
        table_name = "page"


class PageHasTag(ModelBase):
    page = ForeignKeyField(PageModel, backref="tags")
    tag = ForeignKeyField(PageTagModel, backref="pages")

    class Meta:
        table_name = "page_has_tag"


class PageHasUserVote(ModelBase):
    id = (
        AutoField()
    )  # We can't use page+user as primary key because apparently the vote can be anonymous???
    page = ForeignKeyField(PageModel, backref="votes")
    user = ForeignKeyField(UserModel, backref="votes", null=True, default=None)
    vote = BooleanField()  # True is +1, False is -1
    user_unknown = BooleanField(default=False)

    class Meta:
        table_name = "page_vote"


class PageRevisionModel(ModelBase):
    id = AutoField(unique=True)
    revision_id = IntegerField()
    global_id = IntegerField(unique=True)
    author = ForeignKeyField(UserModel, backref="revisions", null=True, default=None)
    timestamp = TimestampField()
    flags = TextField(default="")
    comment = TextField(default="")
    page = ForeignKeyField(PageModel, backref="revisions")

    class Meta:
        table_name = "page_revision"


class ForumPostModel(ModelBase):
    id = AutoField()
    wikidot_id = IntegerField(unique=True)
    title = TextField()
    author = ForeignKeyField(UserModel, backref="forum_posts")
    timestamp = TimestampField()
    last_edit = TimestampField(null=True, default=None)
    last_edit_author = ForeignKeyField(UserModel)
    parent = ForeignKeyField("self", null=True, default=None, backref="children")

    class Meta:
        table_name = "forum_post"


class ForumPostRevisionModel(ModelBase):
    id = AutoField()
    wikidot_id = IntegerField()
    author = ForeignKeyField(UserModel, backref="forum_post_revisions")
    timestamp = TimestampField()
    post = ForeignKeyField(ForumPostModel, backref="revisions")

    class Meta:
        table_name = "forum_post_revision"


class FileModel(ModelBase):
    id = AutoField()
    wikidot_id = IntegerField(unique=True)
    name = TextField()
    url = TextField()
    size_text = TextField()
    size_bytes = IntegerField(null=True, default=None)
    mime_type = TextField()
    description = TextField()
    author = ForeignKeyField(UserModel, backref="uploaded_files")
    upload_time = TimestampField(null=True, default=None)
