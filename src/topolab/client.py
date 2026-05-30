"""Synchronous Topolab client."""
from __future__ import annotations
import os
from urllib.parse import urlparse
from .errors import ConfigurationError
from ._transport import Transport
from .dataset import Dataset
from .datasets import DatasetsNamespace

# Named API environments. Production is the shipped default; staging is one
# keyword away. Self-hosting / tests can still pass an explicit base_url.
ENVIRONMENTS = {
    "production": "https://api.topolab.nl",
    "staging": "https://api-staging.topolab.nl",
}
DEFAULT_BASE_URL = ENVIRONMENTS["production"]

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _environment_url(name: str) -> str:
    try:
        return ENVIRONMENTS[name.lower()]
    except KeyError:
        raise ConfigurationError(
            f"Unknown environment {name!r}. Use one of {sorted(ENVIRONMENTS)}."
        ) from None


def _validate_base_url(url: str) -> str:
    """Reject base URLs that could exfiltrate the API key to an attacker-controlled
    host: require https (http only for loopback), and forbid embedded credentials."""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http"):
        raise ConfigurationError(f"base_url must use http(s); got {url!r}")
    if parsed.username or parsed.password or "@" in parsed.netloc:
        raise ConfigurationError("base_url must not contain credentials (userinfo)")
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise ConfigurationError(f"base_url must use https for non-loopback host {host!r}")
    return url


def resolve_base_url(base_url: str | None, environment: str | None) -> str:
    """Resolve the API base URL. Precedence (most specific first):
    explicit base_url > environment arg > TOPOLAB_BASE_URL > TOPOLAB_ENV > production.

    User-supplied URLs (base_url arg, TOPOLAB_BASE_URL) are validated; the named
    environments and the production default are trusted https constants.
    """
    if base_url:
        return _validate_base_url(base_url.rstrip("/"))
    if environment:
        return _environment_url(environment)
    env_base = os.environ.get("TOPOLAB_BASE_URL")
    if env_base:
        return _validate_base_url(env_base.rstrip("/"))
    env_name = os.environ.get("TOPOLAB_ENV")
    if env_name:
        return _environment_url(env_name)
    return DEFAULT_BASE_URL


class Client:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None,
                 environment: str | None = None, timeout: float = 60.0,
                 max_retries: int = 3, proxy_url: str | None = None,
                 user_agent: str | None = None):
        key = api_key if api_key is not None else os.environ.get("TOPOLAB_API_KEY")
        if not key:
            raise ConfigurationError("No API key. Pass api_key= or set TOPOLAB_API_KEY.")
        self.api_key = key
        self.base_url = resolve_base_url(base_url, environment)
        self._t = Transport(api_key=key, base_url=self.base_url, timeout=timeout,
                            max_retries=max_retries, proxy_url=proxy_url, user_agent=user_agent)
        self.datasets = DatasetsNamespace(self._t)

    def dataset(self, slug: str) -> Dataset:
        return Dataset(self._t, slug)

    def close(self) -> None:
        self._t.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
