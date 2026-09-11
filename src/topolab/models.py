"""Response models. Hand-written Pydantic mirroring openapi.json schemas.

Generation note: ``datamodel-codegen --input ../topolab-sdk-spec/openapi.json
--output src/topolab/_generated.py --output-model-type pydantic_v2.BaseModel``
can regenerate a superset; these focused models are what the client uses.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict, field_validator


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
    # latitude/longitude arrive as fixed-scale decimal strings ("51.49638600")
    # and are kept verbatim: parsing them as floats would drop the trailing
    # zeros and risk representation drift.
    id: str | None = None
    location: dict[str, Any] | None = None
    latitude: str | None = None
    longitude: str | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("latitude", "longitude", mode="before")
    @classmethod
    def _stringify_numbers(cls, v):
        # Tolerate a numeric response rather than failing the whole page;
        # anything else passes through to the declared type.
        return str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v


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
