# wikidash

Incremental archiver for Wikidot wikis. A readable Python rewrite of the SCP-CS fork of
[WikiComma](../wikicomma); it reads and writes the **same archive format**, so existing
backups keep working.

It archives, per wiki: page metadata, votes, tags, files, every revision's source, the
whole forum (categories, threads, posts, post revisions) and the profiles of all users it
meets. Runs are incremental: unchanged pages and threads are skipped.

## Install and run

```
python -m venv .venv && .venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\python -m wikidash [config.json]
```

Config path: argument, else `$WIKICOMMA_CONFIG`, else `./config.json`. Needs Python 3.12+.
No external `7z` binary is needed (`py7zr`).

## Config

Same fields as WikiComma (see `config.example.json`):

| field | meaning |
|---|---|
| `base_directory` | where archives go; each wiki gets `base_directory/<name>/` |
| `wikis[].name`, `wikis[].url` | subdirectory name and wiki root |
| `ratelimit.bucket_size`, `ratelimit.refill_seconds` | per-wiki request budget (burst of `bucket_size`) |
| `delay_ms` | pause before each page job |
| `user_list_cache_freshness` | seconds a user profile counts as fresh (default 86400) |
| `http_proxy`, `socks_proxy` | `{address, port}`; http for `http://` URLs, SOCKS for `https://` |
| `blacklist` | sitemap URLs or page names to skip |
| `scuttle_url` | report progress to SCUTTLE (`POST <url>/backup/status`) |
| `parallel_wikis` | wikis archived at once (default 3, was hard-coded) |

`maximum_jobs` is accepted but unused: the page worker count is fixed at 8.

## Layout of the code

```
config  models  forum_models  user_models      data shapes (JSON-compatible)
paths  store  archive7z  workspace  forum_store   everything that touches the disk
http  ratelimit  retry  ajax  api              talking to Wikidot
parsers/                                        pure HTML -> data functions
sitemap  sync_pages  sync_files  sync_forum  sync_pending   what a run does
userlist  scuttle  progress  runner  cli        glue
```

Parsers never touch network or disk; they report users they see through a callback, and
`UserList` downloads those profiles after the run.

## Differences from the TypeScript version

Bugs fixed on the way:
- revisions of forum posts inside `.7z` archives were invisible, so threads were re-downloaded;
- "very high" user activity was classified as "high";
- file list paging started at page 0 and never stopped on repeated pages;
- removed files and replaced pages were looked up under the wrong directory name;
- state files were written non-atomically; downloads were fire-and-forget;
- an unexpected error in one page worker was silently lost.

Behaviour changes: one retry policy (5 attempts, 5 s apart) instead of "forever" in some
places; a forum thread that keeps failing leaves its category unfinished so the next run
retries it; cookies are not persisted (a fresh token is requested per run).

Dropped: the one-off migration scripts `fixnames`, `fix_rev_usernames`, `fix_forum_usernames`.

## Development

```
.venv\Scripts\python -m pytest
.venv\Scripts\python -m mypy
.venv\Scripts\python -m ruff check .
```

Tests use a fake Wikidot served from memory (`tests/test_runner_e2e.py`) and real metadata
files copied from an original archive (`tests/fixtures`).
