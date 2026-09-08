"""Asynchronous Topolab client. Mirrors Client; methods are awaitable."""
from __future__ import annotations
import os
from typing import Any, AsyncIterator, Sequence
from .errors import ConfigurationError
from ._transport import Transport
from .models import (
    Archive, CoordinatePage, DatasetSummary, DatasetPage, OwnedDataset,
    OwnedDatasets, SqlResult,
)
from .client import resolve_base_url, sql_body
from .dataset import coordinate_page, coordinate_params, validate_month
from .datasets import owned_params

_SAMPLE_FORMATS = {"csv", "json", "geojson", "kml"}
_BULK_FORMATS = {"csv", "json", "geojson", "kml", "shp"}


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


class AsyncDataset:
    def __init__(self, transport: Transport, slug: str) -> None:
        self._t = transport
        self.slug = slug

    async def metadata(self, locale: str | None = None) -> DatasetSummary:
        return DatasetSummary.model_validate(
            await self._t.aget_json(f"/v1/dataset/{self.slug}", params=_clean({"locale": locale})))

    async def sample(self, format: str = "geojson") -> Any:
        if format not in _SAMPLE_FORMATS:
            raise ValueError(f"sample format must be one of {sorted(_SAMPLE_FORMATS)}")
        resp = await self._t.arequest("GET", f"/v1/dataset/{self.slug}/sample/{format}")
        return resp.json() if format in {"json", "geojson"} else resp.text

    async def to_geojson(self) -> dict:
        return await self._t.aget_json(f"/v1/dataset/{self.slug}/files/geojson")

    async def download(self, path: str, format: str = "geojson") -> str:
        if format not in _BULK_FORMATS:
            raise ValueError(f"download format must be one of {sorted(_BULK_FORMATS)}")
        await self._t.astream_to_file(f"/v1/dataset/{self.slug}/files/{format}", path)
        return path

    async def to_geodataframe(self):
        from ._geo import to_geodataframe
        return to_geodataframe(await self.to_geojson())

    async def archives(self) -> list[Archive]:
        body = await self._t.aget_json(f"/v1/dataset/{self.slug}/archives/list")
        return [Archive.model_validate(a) for a in body]

    async def archive(self, path: str, *, month: str = "latest",
                      format: str = "geojson") -> str:
        if format not in _BULK_FORMATS:
            raise ValueError(f"archive format must be one of {sorted(_BULK_FORMATS)}")
        await self._t.astream_to_file(
            f"/v1/dataset/{self.slug}/archives/{validate_month(month)}/{format}", path)
        return path

    async def coordinates(self, *, limit: int | None = None,
                          offset: int | None = None) -> CoordinatePage:
        resp = await self._t.arequest("GET", f"/v1/dataset/{self.slug}/coordinates",
                                      params=coordinate_params(limit, offset))
        return coordinate_page(resp)

    # The OGC collectionId is the dataset slug, so items() addresses the
    # collection by slug directly — no metadata round-trip needed.
    async def items(self, *, bbox: Sequence[float] | None = None, limit: int | None = 100,
                    offset: int | None = None, category: str | None = None,
                    city: str | None = None, country: str | None = None) -> dict:
        p = _clean({"limit": limit, "offset": offset, "category": category,
                    "city": city, "country": country})
        if bbox is not None:
            p["bbox"] = ",".join(str(x) for x in bbox)
        return await self._t.aget_json(f"/v1/ogc/collections/{self.slug}/items", params=p)

    async def iter_items(self, *, page_size: int = 100, total_limit: int | None = None,
                         bbox: Sequence[float] | None = None, category: str | None = None,
                         city: str | None = None, country: str | None = None) -> AsyncIterator[dict]:
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
    def __init__(self, transport: Transport) -> None:
        self._t = transport

    async def list(self, *, page: int | None = None, limit: int | None = None,
                   search: str | None = None, theme: str | None = None,
                   country: str | None = None, sort_by: str | None = None,
                   sort_order: str | None = None) -> DatasetPage:
        params = _clean({"page": page, "limit": limit, "search": search, "theme": theme,
                         "country": country, "sortBy": sort_by, "sortOrder": sort_order})
        return DatasetPage.model_validate(await self._t.aget_json("/v1/dataset/all", params=params))

    async def owned(self, *, limit: int | None = None,
                    offset: int | None = None) -> OwnedDatasets:
        """One page of the datasets this organization licences. `total` counts
        every licensed dataset, not the page."""
        return OwnedDatasets.model_validate(
            await self._t.aget_json("/v1/dataset/owned", params=owned_params(limit, offset)))

    async def iter_owned(self, *, page_size: int = 50,
                         total_limit: int | None = None) -> AsyncIterator[OwnedDataset]:
        yielded = 0
        offset = 0
        while True:
            page = await self.owned(limit=page_size, offset=offset)
            if not page.items:
                return
            for d in page.items:
                yield d
                yielded += 1
                if total_limit is not None and yielded >= total_limit:
                    return
            offset += len(page.items)
            if len(page.items) < page_size or offset >= page.total:
                return


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

    async def sql(self, query: str, *, max_rows: int | None = None) -> SqlResult:
        """Run one read-only SELECT across the datasets you licence. Spans
        datasets, so it lives on the client rather than a dataset handle.
        Requires the `sql-access` entitlement, part of the Enterprise plan."""
        resp = await self._t.arequest("POST", "/v1/sql/query",
                                      json=sql_body(query, max_rows))
        return SqlResult.model_validate(resp.json())

    async def aclose(self):
        await self._t.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()
