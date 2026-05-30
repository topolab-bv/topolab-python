"""Lazy dataset handle (sync). One per slug."""
from __future__ import annotations
from typing import Any, Iterator
from .models import DatasetSummary

_SAMPLE_FORMATS = {"csv", "json", "geojson", "kml"}
_BULK_FORMATS = {"csv", "json", "geojson", "kml", "shp"}


def _clean(params: dict) -> dict:
    return {k: v for k, v in params.items() if v is not None}


class Dataset:
    def __init__(self, transport, slug: str):
        self._t = transport
        self.slug = slug

    # --- metadata / sample ---
    def metadata(self, locale: str | None = None) -> DatasetSummary:
        body = self._t.get_json(f"/v1/dataset/{self.slug}", params=_clean({"locale": locale}))
        return DatasetSummary.model_validate(body)

    def sample(self, format: str = "geojson") -> Any:
        if format not in _SAMPLE_FORMATS:
            raise ValueError(f"sample format must be one of {sorted(_SAMPLE_FORMATS)}")
        resp = self._t.request("GET", f"/v1/dataset/{self.slug}/sample/{format}")
        return resp.json() if format in {"json", "geojson"} else resp.text

    # --- bulk ---
    def to_geojson(self) -> dict:
        return self._t.get_json(f"/v1/dataset/{self.slug}/files/geojson")

    def download(self, path: str, format: str = "geojson") -> str:
        if format not in _BULK_FORMATS:
            raise ValueError(f"download format must be one of {sorted(_BULK_FORMATS)}")
        self._t.stream_to_file(f"/v1/dataset/{self.slug}/files/{format}", path)
        return path

    def to_geodataframe(self):
        from ._geo import to_geodataframe
        return to_geodataframe(self.to_geojson())

    # --- spatial / OGC ---
    # The OGC collectionId is the dataset slug, so items() addresses the
    # collection by slug directly — no metadata round-trip needed.
    def _items_params(self, bbox, limit, offset, category, city, country) -> dict:
        p = {"limit": limit, "offset": offset, "category": category,
             "city": city, "country": country}
        if bbox is not None:
            p["bbox"] = ",".join(str(x) for x in bbox)
        return _clean(p)

    def items(self, *, bbox=None, limit: int | None = 100, offset: int | None = None,
              category=None, city=None, country=None) -> dict:
        return self._t.get_json(
            f"/v1/ogc/collections/{self.slug}/items",
            params=self._items_params(bbox, limit, offset, category, city, country),
        )

    def iter_items(self, *, page_size: int = 100, total_limit: int | None = None,
                   bbox=None, category=None, city=None, country=None) -> Iterator[dict]:
        yielded, offset = 0, 0
        while True:
            params = self._items_params(bbox, page_size, offset, category, city, country)
            fc = self._t.get_json(f"/v1/ogc/collections/{self.slug}/items", params=params)
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
