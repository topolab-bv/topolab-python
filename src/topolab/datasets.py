"""Catalog namespace: tl.datasets.list(...) and tl.datasets.owned(...)."""
from __future__ import annotations
from typing import Iterator
from .models import DatasetPage, OwnedDataset, OwnedDatasets

_OWNED_MAX_LIMIT = 200


def _clean(d):
    return {k: v for k, v in d.items() if v is not None}


def owned_params(limit: int | None, offset: int | None) -> dict:
    if limit is not None and not 1 <= limit <= _OWNED_MAX_LIMIT:
        raise ValueError(f"owned limit must be between 1 and {_OWNED_MAX_LIMIT}")
    if offset is not None and offset < 0:
        raise ValueError("owned offset must be >= 0")
    return _clean({"limit": limit, "offset": offset})


class DatasetsNamespace:
    def __init__(self, transport):
        self._t = transport

    def list(self, *, page=None, limit=None, search=None, theme=None,
             country=None, sort_by=None, sort_order=None) -> DatasetPage:
        params = _clean({"page": page, "limit": limit, "search": search, "theme": theme,
                         "country": country, "sortBy": sort_by, "sortOrder": sort_order})
        return DatasetPage.model_validate(self._t.get_json("/v1/dataset/all", params=params))

    def owned(self, *, limit: int | None = None, offset: int | None = None) -> OwnedDatasets:
        """One page of the datasets this organization licences. `total` counts
        every licensed dataset, not the page."""
        return OwnedDatasets.model_validate(
            self._t.get_json("/v1/dataset/owned", params=owned_params(limit, offset)))

    def iter_owned(self, *, page_size: int = 50,
                   total_limit: int | None = None) -> Iterator[OwnedDataset]:
        yielded, offset = 0, 0
        while True:
            page = self.owned(limit=page_size, offset=offset)
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
