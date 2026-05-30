"""Catalog namespace: tl.datasets.list(...)."""
from __future__ import annotations
from .models import DatasetPage


def _clean(d):
    return {k: v for k, v in d.items() if v is not None}


class DatasetsNamespace:
    def __init__(self, transport):
        self._t = transport

    def list(self, *, page=None, limit=None, search=None, theme=None,
             country=None, sort_by=None, sort_order=None) -> DatasetPage:
        params = _clean({"page": page, "limit": limit, "search": search, "theme": theme,
                         "country": country, "sortBy": sort_by, "sortOrder": sort_order})
        return DatasetPage.model_validate(self._t.get_json("/v1/dataset/all", params=params))
