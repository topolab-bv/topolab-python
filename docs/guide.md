# Guide

## Pull everything you own

The loop this SDK exists for: discover what the organization licences, then pull
each dataset's newest snapshot. No hard-coded slugs.

```python
for ds in tl.datasets.iter_owned():
    tl.dataset(ds.table).archive(f"{ds.table}.zip", month="latest", format="geojson")
```

`owned()` is filtered by the same licence check the download routes enforce, so
everything it returns is downloadable. One page at a time:

```python
page = tl.datasets.owned(limit=50, offset=0)
print(page.total)                 # all licensed datasets, not the page size
for d in page.items:
    print(d.table, d.recordCount, d.latestArchiveMonth)
    print(d.links.current.format(format="csv"))   # links carry a {format} placeholder
```

## Archives

```python
ds = tl.dataset("nl-domino-poi")
for a in ds.archives():           # newest month first
    print(a.month, a.formats)

ds.archive("nl-domino-poi.zip", month="2026-07", format="geojson")
```

`month` takes three forms:

| Value | Meaning |
|---|---|
| `latest` | Newest archive inside your plan's retention window |
| `YYYY-MM` | That month |
| `YYYY-MM-DD` | The month containing that date |

A malformed or impossible month (`2026-13`, `2026-07-99`, `2026-02-29`) raises
`ValueError` before the request is sent; the server answers the same case with a
**400**. A **404** means no archive is available — which also covers months
outside your retention window and months that have not started, deliberately
indistinguishable so the response never reveals an archive you cannot access.

Team plans see a trailing 12 months of archives; Enterprise and full-history
add-ons see everything. `archives()` already reflects your window, so it never
lists a month that would 404.

## Coordinates

Rows arrive as a bare array and the paging facts arrive as response headers; the
SDK folds both into one object.

```python
page = tl.dataset("nl-domino-poi").coordinates(limit=1000, offset=0)
print(page.total, page.returned, page.offset)
row = page.rows[0]
print(row.latitude, row.longitude)     # strings, kept exactly as returned
print(row.location, row.metadata)
```

`limit` caps at 50000. Omit both parameters to take the whole dataset in one
response, up to that cap.

`latitude` and `longitude` are fixed-scale decimal strings (`"51.49638600"`) and
are never parsed as floats — that would drop the trailing zeros and risk
representation drift. Convert them yourself when you need numbers.

## SQL (Enterprise)

```python
res = tl.sql("SELECT city, count(*) AS n FROM nl_domino_poi GROUP BY 1", max_rows=100)
print(res.columns, res.rowCount, res.truncated, res.elapsedMs)
for r in res.rows:
    print(r["city"], r["n"])
```

One read-only `SELECT` (or `WITH`) per call, running against the datasets you
licence. It requires the `sql-access` entitlement, which is part of the
Enterprise plan and is not sold separately; without it the call raises
`AddonRequiredError`. A query that exceeds the server statement timeout raises
`QueryTimeoutError`.

## Browse the catalog

```python
page = tl.datasets.list(country="NL", limit=10)
for d in page.data:
    print(d.table, d.title)
```

## Dataset metadata and samples

```python
ds = tl.dataset("nl-domino-poi")
meta = ds.metadata()           # DatasetSummary
sample = ds.sample("geojson")  # free preview rows (csv/json/geojson/kml)
```

## Query features in an area (spatial, paged)

`items()` addresses the collection by slug directly — the OGC `collectionId`
**is** the dataset slug, so there is no metadata round-trip.

```python
fc = tl.dataset("nl-domino-poi").items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])
```

Stream every feature, paging transparently:

```python
for feature in tl.dataset("nl-domino-poi").iter_items(page_size=500):
    ...
```

## Pull a whole dataset (bulk)

```python
fc = tl.dataset("nl-domino-poi").to_geojson()        # dict (FeatureCollection)
tl.dataset("nl-domino-poi").download("dominos-nl.geojson", format="geojson")
```

`download()` streams to a temp file and atomically renames, so an interrupted
transfer never leaves a truncated file at the destination.

## GeoPandas

With the `geo` extra installed:

```python
gdf = tl.dataset("nl-domino-poi").to_geodataframe()   # geopandas.GeoDataFrame
```

## Async

`AsyncClient` mirrors the sync surface — `metadata`, `sample`, `to_geojson`,
`download`, `to_geodataframe`, `items`, `iter_items`, `archives`, `archive`,
`coordinates`, `datasets.owned`, `datasets.iter_owned` and `sql` are all
awaitable (`iter_items` and `iter_owned` are async iterators):

```python
async with AsyncClient(api_key="tlb_prod_...") as tl:
    ds = tl.dataset("nl-domino-poi")
    fc = await ds.items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])
    await ds.download("dominos-nl.geojson")

    async for owned in tl.datasets.iter_owned():
        await tl.dataset(owned.table).archive(f"{owned.table}.zip")
```
