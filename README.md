# topolab

Official Python client for the [Topolab](https://topolab.nl) dataset and geospatial API.

```bash
pip install topolab          # core (GeoJSON-first, lightweight)
pip install "topolab[geo]"   # adds geopandas for .to_geodataframe()
```

## Quickstart

```python
# Fetch all NL Domino's locations and write to disk
from topolab import Client

tl = Client(api_key="tlb_prod_...")
df = tl.dataset("nl-domino-poi").to_geodataframe()
df.to_file("dominos-nl.geojson")
```

The key carries your scope and addons — bulk downloads need `API_ACCESS`, OGC
feature access needs `GIS_ACCESS`, and data routes require an
organization-scoped key. Set `TOPOLAB_API_KEY` to avoid hard-coding it.

## Browsing the catalog

```python
for ds in tl.datasets.list(country="NL", limit=10).data:
    print(ds.table, ds.metadata)
```

## Spatial queries (paged)

```python
fc = tl.dataset("nl-domino-poi").items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])
for feature in tl.dataset("nl-domino-poi").iter_items(page_size=500):
    ...  # streams every feature, paging transparently
```

## Async

```python
import asyncio
from topolab import AsyncClient

async def main():
    async with AsyncClient() as tl:        # reads TOPOLAB_API_KEY
        md = await tl.dataset("nl-domino-poi").metadata()
        print(md.table)

asyncio.run(main())
```

## Errors

All failures raise a subclass of `TopolabError` (`AuthenticationError`,
`AddonRequiredError`, `AccessDeniedError`, `InsufficientCreditsError`,
`NotFoundError`, `RateLimitError`, …). `AddonRequiredError.addon` names the
missing addon; `InsufficientCreditsError` carries `required`/`available`.

MIT licensed.
