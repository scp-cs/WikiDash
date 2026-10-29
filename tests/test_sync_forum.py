import json
from pathlib import Path

from fakes_forum import FakeForum
from wikidash.forum_models import CategoryInfo, PostInfo, PostRevision, ThreadInfo
from wikidash.forum_store import ForumStore
from wikidash.sync_forum import ForumSyncer


def thread(thread_id: int, last: int, posts: int) -> ThreadInfo:
    return ThreadInfo(thread_id, f"T{thread_id}", "d", posts, False, 1, 7, last, 7)


def post(post_id: int, edited: bool = False, children: list[PostInfo] | None = None) -> PostInfo:
    return PostInfo(
        id=post_id,
        title=f"P{post_id}",
        poster=7,
        content=f"<p>post {post_id}</p>",
        stamp=10,
        last_edit=20 if edited else None,
        last_edit_by=7 if edited else None,
        children=children or [],
    )


def make_forum() -> FakeForum:
    forum = FakeForum()
    forum.categories[1] = CategoryInfo(1, "General", "d", threads=3, posts=4, last=100, last_user=7)
    forum.threads[1] = [thread(11, 100, 3), thread(12, 90, 1), thread(13, 80, 0)]
    forum.posts[11] = [post(111, edited=True, children=[post(112)]), post(113)]
    forum.posts[12] = [post(121)]
    forum.posts[13] = []
    forum.revisions[111] = [PostRevision(1001, 7, 10), PostRevision(1002, 7, 20)]
    return forum


def make_syncer(tmp_path: Path, forum: FakeForum) -> tuple[ForumSyncer, ForumStore]:
    store = ForumStore(tmp_path)
    return ForumSyncer(store, forum, workers=2), store


def test_first_sync_stores_everything(tmp_path: Path) -> None:
    forum = make_forum()
    syncer, store = make_syncer(tmp_path, forum)
    assert syncer.sync_all() is True

    meta = store.read_thread(1, 11)
    assert meta is not None and meta.posts_num == 3
    assert [p.id for p in meta.all_posts()] == [111, 112, 113]
    assert sorted(r.id for r in meta.posts[0].revisions) == [1001, 1002]
    assert store.known_html(1, 11)[111] == {"latest", "1001", "1002"}
    assert not (tmp_path / "forum" / "1" / "11").exists()  # compressed
    assert (tmp_path / "forum" / "1" / "11.7z").is_file()

    category = json.loads((tmp_path / "meta" / "forum" / "category" / "1.json").read_text())
    assert (category["full_scan"], category["last_page"]) == (True, 0)


def test_unchanged_forum_is_skipped(tmp_path: Path) -> None:
    forum = make_forum()
    syncer, _ = make_syncer(tmp_path, forum)
    syncer.sync_all()
    forum.calls.clear()
    syncer.sync_all()
    assert forum.calls == []


def test_changed_thread_reuses_archived_revisions(tmp_path: Path) -> None:
    forum = make_forum()
    syncer, store = make_syncer(tmp_path, forum)
    syncer.sync_all()
    forum.calls.clear()

    forum.categories[1].last = 200
    forum.threads[1][0] = thread(11, 200, 4)
    forum.posts[11].append(post(114))
    syncer.sync_all()

    assert forum.calls == ["posts:11"]  # revisions of 111 are already in the .7z
    meta = store.read_thread(1, 11)
    assert meta is not None and [p.id for p in meta.all_posts()] == [111, 112, 113, 114]
    assert sorted(r.id for r in meta.posts[0].revisions) == [1001, 1002]


def test_failed_thread_keeps_category_incomplete(tmp_path: Path) -> None:
    forum = make_forum()
    forum.failing_threads = {12}
    syncer, store = make_syncer(tmp_path, forum)
    assert syncer.sync_all() is False
    category = store.read_category(1)
    assert category is not None and category.full_scan is False

    forum.failing_threads = set()
    assert syncer.sync_all() is True
    assert store.read_thread(1, 12) is not None
    category = store.read_category(1)
    assert category is not None and category.full_scan is True


def test_internal_error_revision_is_skipped(tmp_path: Path) -> None:
    forum = make_forum()
    forum.internal_error_revisions = {1001}
    syncer, store = make_syncer(tmp_path, forum)
    assert syncer.sync_all() is True
    meta = store.read_thread(1, 11)
    assert meta is not None and [r.id for r in meta.posts[0].revisions] == [1002]
