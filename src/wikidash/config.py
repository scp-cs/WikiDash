"""Daemon configuration (same JSON fields as the original WikiComma)."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = "config.json"
CONFIG_ENV_VAR = "WIKICOMMA_CONFIG"
DEFAULT_USER_CACHE_SECONDS = 86400


@dataclass(frozen=True)
class WikiConfig:
    name: str  # subdirectory name inside base_directory
    url: str  # wiki root, without trailing slash


@dataclass(frozen=True)
class RateLimitConfig:
    bucket_size: int
    refill_seconds: float


@dataclass(frozen=True)
class ProxyConfig:
    address: str
    port: int


@dataclass(frozen=True)
class Config:
    base_directory: Path
    wikis: list[WikiConfig]
    ratelimit: RateLimitConfig | None = None
    delay_ms: int = 0
    maximum_jobs: int | None = None
    parallel_wikis: int = 3
    user_list_cache_freshness: int = DEFAULT_USER_CACHE_SECONDS  # seconds
    http_proxy: ProxyConfig | None = None
    socks_proxy: ProxyConfig | None = None
    blacklist: list[str] = field(default_factory=list)
    scuttle_url: str | None = None

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Config":
        return cls(
            base_directory=Path(raw["base_directory"]),
            wikis=[
                # Wikidot dislikes double slashes, so strip a trailing one.
                WikiConfig(name=w["name"], url=w["url"].rstrip("/"))
                for w in raw["wikis"]
            ],
            ratelimit=RateLimitConfig(**raw["ratelimit"]) if raw.get("ratelimit") else None,
            delay_ms=raw.get("delay_ms") or 0,
            maximum_jobs=raw.get("maximum_jobs"),
            parallel_wikis=raw.get("parallel_wikis", 3),
            user_list_cache_freshness=raw.get(
                "user_list_cache_freshness", DEFAULT_USER_CACHE_SECONDS
            ),
            http_proxy=ProxyConfig(**raw["http_proxy"]) if raw.get("http_proxy") else None,
            socks_proxy=ProxyConfig(**raw["socks_proxy"]) if raw.get("socks_proxy") else None,
            blacklist=raw.get("blacklist") or [],
            scuttle_url=raw.get("scuttle_url"),
        )


def load_config(path: str | None = None) -> Config:
    """Load config from `path`, else $WIKICOMMA_CONFIG, else ./config.json."""
    resolved = path or os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_PATH
    with open(resolved, encoding="utf-8") as file:
        return Config.from_dict(json.load(file))
