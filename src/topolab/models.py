"""Response models. Hand-written Pydantic mirroring openapi.json schemas.

Generation note: ``datamodel-codegen --input ../topolab-sdk-spec/openapi.json
--output src/topolab/_generated.py --output-model-type pydantic_v2.BaseModel``
can regenerate a superset; these focused models are what the client uses.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, PrivateAttr, model_serializer, model_validator


class _Loose(BaseModel):
    model_config = ConfigDict(extra="allow")


class DatasetSummary(_Loose):
    id: str
    table: str
    theme: str | None = None
    country: str | None = None
    metadata: dict[str, Any] | None = None


class PageMeta(_Loose):
    currentPage: int = 0
    itemsPerPage: int = 0
    totalItems: int = 0
    totalPages: int = 0
    hasPreviousPage: bool = False
    hasNextPage: bool = False


class DatasetPage(BaseModel):
    data: list[DatasetSummary]
    meta: PageMeta


class OwnedDatasetLinks(_Loose):
    """Absolute URLs. `current` and `latestArchive` carry a literal `{format}`."""
    current: str | None = None
    archives: str | None = None
    latestArchive: str | None = None


class OwnedDataset(_Loose):
    table: str
    name: str
    recordCount: int | None = None
    latestArchiveMonth: str | None = None
    latestArchiveFormats: list[str] = []
    archiveMonthsAvailable: int = 0
    links: OwnedDatasetLinks = OwnedDatasetLinks()


class OwnedDatasets(BaseModel):
    items: list[OwnedDataset]
    total: int          # all licensed datasets, not the size of this page
    limit: int
    offset: int


class Archive(_Loose):
    month: str
    formats: list[str] = []
    archiveDate: str | None = None


class CoordinateRow(_Loose):
    """One record of the coordinates route as a flat row: the free sample's row
    for your tier plus the record's ``id``.

    The fixed keys are typed fields. Every other key is one of the dataset's
    columns, kept as it arrived: read it as an attribute (``row.city``) or from
    ``row.model_extra``. The columns vary per dataset and tier; the dataset
    detail (``GET /v1/dataset/{table}``) describes them in ``columns``. An empty
    value is ``None`` and a list (``tags``, ``category_path``) is a list.

    ``model_dump()`` returns the whole row in the order the API sent it: ``id``
    first, ``latitude`` and ``longitude`` directly after ``location_name``,
    ``geo_type`` after the dataset's columns, and ``geometry`` last.
    """
    id: str
    # WGS 84, None for a record with no position. Decimal text from an older
    # server is read as a number too.
    latitude: float | None = None
    longitude: float | None = None
    # The served geometry's type in upper case: "POINT" on this route.
    geo_type: str | None = None
    # GeoJSON Point, coordinates [longitude, latitude].
    geometry: dict[str, Any] | None = None

    _keys: list[str] = PrivateAttr(default_factory=list)

    @model_validator(mode="wrap")
    @classmethod
    def _remember_key_order(cls, data: Any, handler):
        row = handler(data)
        if isinstance(data, dict):
            row._keys = list(data)
        return row

    @model_serializer(mode="wrap")
    def _dump_in_key_order(self, handler):
        # Declared fields would otherwise come first and the dataset's columns
        # after them; put every key back where the API sent it.
        out = handler(self)
        if not isinstance(out, dict):
            return out
        known = [k for k in self._keys if k in out]
        return {k: out[k] for k in known + [k for k in out if k not in self._keys]}


class CoordinatePage(BaseModel):
    """Rows plus the paging facts the route returns as X-* response headers."""
    rows: list[CoordinateRow]
    total: int
    returned: int
    offset: int


class SqlResult(_Loose):
    columns: list[str] = []
    rows: list[dict[str, Any]] = []
    rowCount: int = 0
    truncated: bool = False
    elapsedMs: float = 0.0
    datasets: list[str] = []
