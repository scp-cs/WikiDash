"""Command line entry point: `wikidash [config.json]`."""

import argparse
import logging
import sys

from .config import Config, WikiConfig, load_config
from .logging import create_logger
from .progress import StatusSink
from .runner import WikiRunner, make_client, run_all
from .scuttle import ScuttleConnector
from .userlist import UserList


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wikidash", description="Archive Wikidot wikis.")
    parser.add_argument("config", nargs="?", help="config file (default: $WIKICOMMA_CONFIG or config.json)")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    create_logger(None)
    
    try:
        config = load_config(args.config)
    except (OSError, ValueError, KeyError) as err:
        print(f"Cannot load config: {err}", file=sys.stderr)
        print("Pass a path or set the WIKICOMMA_CONFIG environment variable.", file=sys.stderr)
        return 1

    if config.debug_config:
        logging.getLogger('httpx').setLevel(logging.INFO if config.debug_config.httpx_logging else logging.WARNING)

    return archive(config)


def archive(config: Config) -> int:
    # Users are shared by all wikis and fetched from www.wikidot.com with their own limiter.
    users = UserList(
        config.base_directory / "_users",
        make_client(config),
        cache_seconds=config.user_list_cache_freshness,
    )

    def make_runner(wiki: WikiConfig) -> WikiRunner:
        status = (
            ScuttleConnector(wiki.name, config.scuttle_url) if config.scuttle_url else StatusSink()
        )
        return WikiRunner(wiki, config, make_client(config), users, status)

    failed = run_all(config, make_runner)
    users.fetch_pending()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
