from datetime import datetime

from peewee import Database

from .sqlite_models import (
    PageHasTag,
    PageHasUserVote,
    PageModel,
    PageRevisionModel,
    PageTagModel,
    UserModel,
)

from .models import PageMeta, PageRevision

ALL_MODELS = [
    UserModel,
    PageModel,
    PageTagModel,
    PageRevisionModel,
    PageHasTag,
    PageHasUserVote
]

def create_tables(database: Database) -> None:
    database.create_tables(ALL_MODELS)

def bind_tables(database: Database) -> None:
    database.bind(ALL_MODELS)

def save_page_revision(database: Database, revision: PageRevision, page: PageMeta) -> None:
    # TODO: The users will be fetched out-of-order with revisions so we can't guarantee that the author will be in the database here
    # We have to store everything in a queue somewhere and then flush it into the database when all fetching is done in the right order
    PageRevisionModel.insert(revision_id = revision.revision,
                             global_id = revision.global_revision,
                             author = UserModel.get_or_none(UserModel.wikidot_id == revision.author),
                             timestamp = datetime.fromtimestamp(revision.stamp or 0),
                             flags = revision.flags,
                             comment = revision.commentary,
                             page = PageModel.get_or_none(PageModel.wikidot_id == page.page_id))