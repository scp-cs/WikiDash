"""HTTP client: rate limiting, proxies, cookies and retry on network errors."""

from pathlib import Path
from typing import Any
from random_user_agent.user_agent import UserAgent
from random_user_agent.params import OperatingSystem, Popularity, SoftwareName

import httpx

from .config import ProxyConfig
from .errors import HttpError
from .ratelimit import RateLimiter
from .retry import retry
from .store import read_json, write_json

DEFAULT_CONNECTIONS = 8
DEFAULT_TIMEOUT = 30.0
_OK_STATUSES = (200, 206)

# Wikidot serves some pages (and file downloads) only to browser-like agents.
AGENT_SOFTWARE_NAMES = [SoftwareName.CHROME.value, 
                        SoftwareName.CHROMIUM.value, 
                        SoftwareName.EDGE.value, 
                        SoftwareName.BRAVE.value, 
                        SoftwareName.OPERA.value, 
                        SoftwareName.FIREFOX.value, 
                        SoftwareName.SAFARI.value]

AGENT_OS = [OperatingSystem.ANDROID.value, 
            OperatingSystem.DARWIN.value, 
            OperatingSystem.WINDOWS.value, 
            OperatingSystem.LINUX.value]

AGENT_POPULARITY = [Popularity.POPULAR.value, 
                    Popularity.COMMON.value]

agent_rotator = UserAgent(software_names=AGENT_SOFTWARE_NAMES, operating_system=AGENT_SOFTWARE_NAMES, popularity=AGENT_POPULARITY, limit=50)

class HttpClient:
    """Sync HTTP client. Thread-safe: httpx.Client is, and the limiter locks."""

    def __init__(
        self,
        *,
        limiter: RateLimiter | None = None,
        connections: int = DEFAULT_CONNECTIONS,
        http_proxy: ProxyConfig | None = None,
        socks_proxy: ProxyConfig | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._limiter = limiter
        limits = httpx.Limits(max_connections=connections)
        self._client = httpx.Client(
            headers={"User-Agent": agent_rotator.get_random_user_agent(), "Accept": "*/*"},
            limits=limits,
            timeout=timeout,
            transport=transport,
            mounts=None if transport else _proxy_mounts(http_proxy, socks_proxy, limits),
        )

    def get(
        self, url: str, *, headers: dict[str, str] | None = None, follow_redirects: bool = True
    ) -> bytes:
        return self._request("GET", url, headers=headers, follow_redirects=follow_redirects)

    def post(
        self, url: str, *, data: dict[str, Any], headers: dict[str, str] | None = None
    ) -> bytes:
        return self._request("POST", url, data=data, headers=headers, follow_redirects=False)

    def close(self) -> None:
        self._client.close()

    # --- cookies -------------------------------------------------------

    def get_cookie(self, name: str) -> str | None:
        for cookie in self._client.cookies.jar:
            if cookie.name == name:
                return cookie.value
        return None

    def delete_cookie(self, name: str) -> None:
        for cookie in list(self._client.cookies.jar):
            if cookie.name == name:
                self._client.cookies.jar.clear(cookie.domain, cookie.path, cookie.name)

    def load_cookies(self, path: Path) -> None:
        if not path.exists():
            return
        for item in read_json(path):
            self._client.cookies.set(
                item["name"], item["value"], domain=item["domain"], path=item["path"]
            )

    def save_cookies(self, path: Path) -> None:
        write_json(
            path,
            [
                {"name": c.name, "value": c.value, "domain": c.domain, "path": c.path}
                for c in self._client.cookies.jar
                if c.value is not None
            ],
        )

    # --- internals -----------------------------------------------------

    @retry(attempts=3, delay=1.0, on=httpx.TransportError)
    def _request(
        self, method: str, url: str, *, follow_redirects: bool, **kwargs: Any
    ) -> bytes:
        # Each attempt spends a token: a retry is a real request to the server.
        if self._limiter is not None:
            self._limiter.acquire()
        response = self._client.request(method, url, follow_redirects=follow_redirects, **kwargs)
        if response.status_code in _OK_STATUSES or (
            not follow_redirects and response.is_redirect
        ):
            return response.content
        raise HttpError(response.status_code, url, response.content)


def _proxy_mounts(
    http_proxy: ProxyConfig | None, socks_proxy: ProxyConfig | None, limits: httpx.Limits
) -> dict[str, httpx.BaseTransport] | None:
    """http:// goes through the HTTP proxy, https:// through the SOCKS proxy."""
    mounts: dict[str, httpx.BaseTransport] = {}
    if http_proxy:
        proxy = f"http://{http_proxy.address}:{http_proxy.port}"
        mounts["http://"] = httpx.HTTPTransport(proxy=proxy, limits=limits)
    if socks_proxy:
        proxy = f"socks5://{socks_proxy.address}:{socks_proxy.port}"
        mounts["https://"] = httpx.HTTPTransport(proxy=proxy, limits=limits)
    return mounts or None
