"""Response models. Hand-written Pydantic mirroring openapi.json schemas.

Generation note: ``datamodel-codegen --input ../topolab-sdk-spec/openapi.json
--output src/topolab/_generated.py --output-model-type pydantic_v2.BaseModel``
can regenerate a superset; these focused models are what the client uses.
"""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, ConfigDict


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
