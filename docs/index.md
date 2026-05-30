# Topolab Python SDK

`topolab` is a lightweight, GeoJSON-first client over the [Topolab](https://topolab.nl)
dataset and geospatial API. It wraps dataset metadata, samples, bulk downloads, and
the OGC API - Features endpoints, and converts results to GeoPandas on request.

!!! info "Full platform docs"
    This site is the technical reference for the Python package. The full platform
    documentation lives at [docs.topolab.nl](https://docs.topolab.nl).

## Install

```bash
pip install topolab          # core — GeoJSON-first, minimal dependencies
pip install "topolab[geo]"   # adds GeoPandas for .to_geodataframe()
```

> **Pre-release:** until the first version is published to PyPI, install from Git:
> `pip install "git+https://github.com/topolab-bv/topolab-python.git"`

Requires Python 3.10+.

## Quickstart

```python
from topolab import Client

# Page Domino's locations within an Amsterdam bounding box
tl = Client(api_key="tlb_prod_...")
fc = tl.dataset("nl-domino-poi").items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])
print(f"{len(fc['features'])} locations")
```

Your API key carries your scope and add-ons — spatial queries need `GIS_ACCESS`,
downloads need `API_ACCESS`, and data routes require an organization-scoped key.
Prefer the environment over hard-coding:

```python
import os
from topolab import Client

tl = Client(api_key=os.environ["TOPOLAB_API_KEY"])
```

## Staging vs production

The client targets **production** (`https://api.topolab.nl`) by default. Switch with
the `environment` option:

```python
tl = Client(api_key="tlb_staging_...", environment="staging")  # https://api-staging.topolab.nl
```

Or set `TOPOLAB_ENV=staging`. An explicit `base_url` always wins. Precedence:
`base_url` → `environment` → `TOPOLAB_BASE_URL` → `TOPOLAB_ENV` → production.

## Async

Every call has an awaitable equivalent on `AsyncClient`, with the same surface:

```python
import asyncio
from topolab import AsyncClient

async def main():
    async with AsyncClient(api_key="tlb_prod_...") as tl:
        async for feature in tl.dataset("nl-domino-poi").iter_items(page_size=500):
            ...

asyncio.run(main())
```
