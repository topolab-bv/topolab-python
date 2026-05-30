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
| `tl.dataset(slug)` | `Dataset` | Lazy handle for one dataset |

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

On `AsyncClient`, every `Dataset` method is awaitable and `iter_items` is an
async iterator.

## Collections are addressed by slug

The OGC `collectionId` is the dataset's `table` slug (e.g. `nl-domino-poi`) — the
same value you pass to `dataset()`. The SDK calls
`/v1/ogc/collections/{slug}/items` directly; there is no slug→uuid resolution
step.
