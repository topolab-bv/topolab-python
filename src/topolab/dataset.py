"""Lazy dataset handle (sync). One per slug."""
from __future__ import annotations
import re
from datetime import date
from typing import Any, Iterator
from .models import Archive, CoordinatePage, DatasetSummary

_SAMPLE_FORMATS = {"csv", "json", "geojson", "kml"}
_BULK_FORMATS = {"csv", "json", "geojson", "kml", "shp"}
_MONTH_RE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?$")
_COORDINATES_MAX_LIMIT = 50000


def _clean(params: dict) -> dict:
    return {k: v for k, v in params.items() if v is not None}


def validate_month(month: str) -> str:
    """Accept `latest`, `YYYY-MM` or `YYYY-MM-DD`, as a real calendar value —
    `2026-13`, `2026-07-99` and `2026-02-29` are rejected. The server applies
    the same rule and answers 400, so failing here saves a round trip."""
    if month.lower() == "latest":
        return "latest"
    m = _MONTH_RE.match(month)
    if m:
        try:
            date(int(m[1]), int(m[2]), int(m[3]) if m[3] else 1)
            return month
        except ValueError:
            pass
    raise ValueError(f'month must be "latest", YYYY-MM or YYYY-MM-DD; got {month!r}')


def coordinate_params(limit: int | None, offset: int | None) -> dict:
    if limit is not None and not 1 <= limit <= _COORDINATES_MAX_LIMIT:
        raise ValueError(f"coordinates limit must be between 1 and {_COORDINATES_MAX_LIMIT}")
    if offset is not None and offset < 0:
        raise ValueError("coordinates offset must be >= 0")
    return _clean({"limit": limit, "offset": offset})


def _int_header(headers, name: str, default: int) -> int:
    try:
        return int(headers.get(name))
    except (AttributeError, TypeError, ValueError):
        return default


def coordinate_page(resp) -> CoordinatePage:
    """Rows come back as a bare array; the paging facts ride on the headers."""
    rows = resp.json()
    h = getattr(resp, "headers", {}) or {}
    return CoordinatePage(
        rows=rows,
        total=_int_header(h, "x-total-count", len(rows)),
        returned=_int_header(h, "x-returned-count", len(rows)),
        offset=_int_header(h, "x-offset", 0),
    )


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

    # --- archives ---
    def archives(self) -> list[Archive]:
        body = self._t.get_json(f"/v1/dataset/{self.slug}/archives/list")
        return [Archive.model_validate(a) for a in body]

    def archive(self, path: str, *, month: str = "latest", format: str = "geojson") -> str:
        if format not in _BULK_FORMATS:
            raise ValueError(f"archive format must be one of {sorted(_BULK_FORMATS)}")
        self._t.stream_to_file(
            f"/v1/dataset/{self.slug}/archives/{validate_month(month)}/{format}", path)
        return path

    # --- coordinates ---
    def coordinates(self, *, limit: int | None = None, offset: int | None = None) -> CoordinatePage:
        resp = self._t.request("GET", f"/v1/dataset/{self.slug}/coordinates",
                               params=coordinate_params(limit, offset))
        return coordinate_page(resp)

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
