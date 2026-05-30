"""Asynchronous Topolab client. Mirrors Client; methods are awaitable."""
from __future__ import annotations
import os
from typing import AsyncIterator
from .errors import ConfigurationError
from ._transport import Transport
from .models import DatasetSummary, DatasetPage
from .client import resolve_base_url


def _clean(d):
    return {k: v for k, v in d.items() if v is not None}


class AsyncDataset:
    def __init__(self, transport, slug: str):
        self._t = transport
        self.slug = slug

    async def metadata(self, locale: str | None = None) -> DatasetSummary:
        return DatasetSummary.model_validate(
            await self._t.aget_json(f"/v1/dataset/{self.slug}", params=_clean({"locale": locale})))

    async def to_geojson(self) -> dict:
        return await self._t.aget_json(f"/v1/dataset/{self.slug}/files/geojson")

    # The OGC collectionId is the dataset slug, so items() addresses the
    # collection by slug directly — no metadata round-trip needed.
    async def items(self, *, bbox=None, limit=100, offset=None,
                    category=None, city=None, country=None) -> dict:
        p = _clean({"limit": limit, "offset": offset, "category": category,
                    "city": city, "country": country})
        if bbox is not None:
            p["bbox"] = ",".join(str(x) for x in bbox)
        return await self._t.aget_json(f"/v1/ogc/collections/{self.slug}/items", params=p)

    async def iter_items(self, *, page_size=100, total_limit=None, bbox=None,
                         category=None, city=None, country=None) -> AsyncIterator[dict]:
        yielded = 0
        offset = 0
        while True:
            p = _clean({"limit": page_size, "offset": offset, "category": category,
                        "city": city, "country": country})
            if bbox is not None:
                p["bbox"] = ",".join(str(x) for x in bbox)
            fc = await self._t.aget_json(f"/v1/ogc/collections/{self.slug}/items", params=p)
            feats = fc.get("features", [])
            if not feats:
                return
            for f in feats:
                yield f
                yielded += 1
                if total_limit is not None and yielded >= total_limit:
                    return
            if len(feats) < page_size:
                return
            offset += page_size


class AsyncDatasetsNamespace:
    def __init__(self, transport):
        self._t = transport

    async def list(self, *, page=None, limit=None, search=None, theme=None,
                   country=None, sort_by=None, sort_order=None) -> DatasetPage:
        params = _clean({"page": page, "limit": limit, "search": search, "theme": theme,
                         "country": country, "sortBy": sort_by, "sortOrder": sort_order})
        return DatasetPage.model_validate(await self._t.aget_json("/v1/dataset/all", params=params))


class AsyncClient:
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
        self.datasets = AsyncDatasetsNamespace(self._t)

    def dataset(self, slug: str) -> AsyncDataset:
        return AsyncDataset(self._t, slug)

    async def aclose(self):
        await self._t.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()
