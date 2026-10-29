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


class UserModel(Model):
    id = AutoField()
    wikidot_id = IntegerField()
    username = CharField(512)
    user_since = DateTimeField()
    activity = IntegerField()
    real_name = TextField(null=True, default=None)
    gender = TextField(null=True, default=None)
    birthday = DateTimeField(null=True, default=None)
    location = TextField(null=True, default=None)
    website = TextField(null=True, default=None)
    bio = TextField(null=True, default=None)
    account_type = TextField(null=True, default=None)

class ForumThreadModel(Model):
    pass

class PageTagModel(Model):
    id = AutoField()
    text = TextField()

class PageModel(Model):
    id = AutoField()
    name = TextField()
    wikidot_id = IntegerField()
    title = TextField(null=True, default=None)
    sitemap_update = DateTimeField(null=True, default=None)
    version = IntegerField(default=0)
    parent = ForeignKeyField('self', null=True, default=None, backref='children')
    rating = IntegerField(default=0)
    forum_thread = ForeignKeyField(ForumThreadModel, null=True, default=None, backref='page')
    locked = BooleanField(null=True, default=None)

class PageHasTag(Model):
    page = ForeignKeyField(PageModel, backref='tags')
    tag = ForeignKeyField(PageTagModel, backref='pages')

class PageHasUserVote(Model):
    page = ForeignKeyField(PageModel, backref='votes')
    user = ForeignKeyField(UserModel, backref='votes')
    vote = BooleanField() # True is +1, False is -1

class PageRevisionModel(Model):
    id = AutoField()
    revision_id = IntegerField()
    global_id = IntegerField()
    author = ForeignKeyField(UserModel, backref='revisions', null=True, default=None)
    timestamp = TimestampField()
    flags = TextField(default="")
    comment = TextField(default="")
    page = ForeignKeyField(PageModel, backref='revisions')


# ======= Forum models go here later ======