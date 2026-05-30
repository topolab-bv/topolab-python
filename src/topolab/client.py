"""Synchronous Topolab client."""
from __future__ import annotations
import os
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


def _environment_url(name: str) -> str:
    try:
        return ENVIRONMENTS[name.lower()]
    except KeyError:
        raise ConfigurationError(
            f"Unknown environment {name!r}. Use one of {sorted(ENVIRONMENTS)}."
        ) from None


def resolve_base_url(base_url: str | None, environment: str | None) -> str:
    """Resolve the API base URL. Precedence (most specific first):
    explicit base_url > environment arg > TOPOLAB_BASE_URL > TOPOLAB_ENV > production.
    """
    if base_url:
        return base_url.rstrip("/")
    if environment:
        return _environment_url(environment)
    env_base = os.environ.get("TOPOLAB_BASE_URL")
    if env_base:
        return env_base.rstrip("/")
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
