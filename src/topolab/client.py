"""Synchronous Topolab client."""
from __future__ import annotations
import os
from .errors import ConfigurationError
from ._transport import Transport
from .dataset import Dataset
from .datasets import DatasetsNamespace

DEFAULT_BASE_URL = "https://api.topolab.nl"


class Client:
    def __init__(self, api_key: str | None = None, *, base_url: str | None = None,
                 timeout: float = 60.0, max_retries: int = 3,
                 proxy_url: str | None = None, user_agent: str | None = None):
        key = api_key if api_key is not None else os.environ.get("TOPOLAB_API_KEY")
        if not key:
            raise ConfigurationError("No API key. Pass api_key= or set TOPOLAB_API_KEY.")
        self.api_key = key
        self.base_url = base_url or os.environ.get("TOPOLAB_BASE_URL") or DEFAULT_BASE_URL
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
