# API reference

## `Client` / `AsyncClient`

```python
Client(
    api_key: str | None = None,   # defaults to $TOPOLAB_API_KEY
    *,
    base_url: str | None = None,  # explicit override (wins over environment)
    environment: str | None = None,  # "production" (default) | "staging"
    timeout: float = 60.0,
    max_retries: int = 3,
    proxy_url: str | None = None,
    user_agent: str | None = None,
)
```

`AsyncClient` takes the same arguments and is an async context manager
(`async with AsyncClient(...) as tl: ...`) or close with `await tl.aclose()`.

| Member | Returns | Notes |
|---|---|---|
| `tl.datasets.list(*, page, limit, search, theme, country, sort_by, sort_order)` | `DatasetPage` | Catalog listing |
| `tl.datasets.owned(*, limit=None, offset=None)` | `OwnedDatasets` | Datasets your organization licences; `limit` 1–200 (server default 50), `offset` ≥ 0 |
| `tl.datasets.iter_owned(*, page_size=50, total_limit=None)` | iterator of `OwnedDataset` | Pages `owned()` by offset until `total` is reached |
| `tl.dataset(slug)` | `Dataset` | Lazy handle for one dataset |
| `tl.sql(query, *, max_rows=None)` | `SqlResult` | Read-only SELECT across licensed datasets; needs the Enterprise `sql-access` entitlement |

## `Dataset` / `AsyncDataset`

| Method | Returns | Notes |
|---|---|---|
| `.metadata(locale=None)` | `DatasetSummary` | Dataset metadata |
| `.sample(format="geojson")` | `dict` \| `str` | Free preview; `csv`/`json`/`geojson`/`kml` |
| `.to_geojson()` | `dict` | Full dataset (requires `API_ACCESS`) |
| `.download(path, format="geojson")` | `str` | Streamed; `csv`/`json`/`geojson`/`kml`/`shp` |
| `.to_geodataframe()` | `geopandas.GeoDataFrame` | Requires the `geo` extra |
| `.items(*, bbox, limit=100, offset, category, city, country)` | `dict` | One page of OGC features |
| `.iter_items(*, page_size=100, total_limit=None, bbox, category, city, country)` | iterator of `dict` | Auto-paginates |
| `.archives()` | `list[Archive]` | Available monthly archives, newest first |
| `.archive(path, *, month="latest", format="geojson")` | `str` | Streams one monthly archive (zip) to `path` |
| `.coordinates(*, limit=None, offset=None)` | `CoordinatePage` | Coordinate rows; `limit` ≤ 50000, `offset` ≥ 0 |

On `AsyncClient`, every `Dataset` method is awaitable and `iter_items` is an
async iterator.

## Collections are addressed by slug

The OGC `collectionId` is the dataset's `table` slug (e.g. `nl-domino-poi`) — the
same value you pass to `dataset()`. The SDK calls
`/v1/ogc/collections/{slug}/items` directly; there is no slug→uuid resolution
step.

## Models

| Model | Fields |
|---|---|
| `OwnedDatasets` | `items: list[OwnedDataset]`, `total`, `limit`, `offset` — `total` counts **all** licensed datasets, not the page |
| `OwnedDataset` | `table`, `name`, `recordCount`, `latestArchiveMonth`, `latestArchiveFormats`, `archiveMonthsAvailable`, `links` |
| `OwnedDatasetLinks` | `current`, `archives`, `latestArchive` — absolute URLs; `current` and `latestArchive` contain a literal `{format}` placeholder, and `latestArchive` is `None` when no archive is in range |
| `Archive` | `month` (`YYYY-MM`), `formats`, `archiveDate` |
| `CoordinatePage` | `rows: list[CoordinateRow]`, `total`, `returned`, `offset` — the counts come from the `X-Total-Count` / `X-Returned-Count` / `X-Offset` response headers |
| `CoordinateRow` | `id`, `location` (GeoJSON geometry), `latitude`, `longitude`, `metadata` — `latitude`/`longitude` are **strings**, kept verbatim (a numeric value is stringified, never parsed as a float) |
| `SqlResult` | `columns`, `rows`, `rowCount`, `truncated`, `elapsedMs`, `datasets` |

Models ignore nothing: unknown fields the API adds later are preserved rather
than dropped.

## Addressing an archive

`month` accepts `latest`, `YYYY-MM`, or `YYYY-MM-DD` (the month containing that
date). The value is checked as a real calendar value before the request goes
out, so `2026-13`, `2026-07-99` and `2026-02-29` raise `ValueError` locally
instead of costing a round trip.
