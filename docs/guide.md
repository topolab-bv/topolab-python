# Guide

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
`download`, `to_geodataframe`, `items`, and `iter_items` are all awaitable:

```python
async with AsyncClient(api_key="tlb_prod_...") as tl:
    ds = tl.dataset("nl-domino-poi")
    fc = await ds.items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])
    await ds.download("dominos-nl.geojson")
```
