<p align="center">
  <img src="assets/topolab-logo.png" alt="Topolab" width="320">
</p>

<p align="center">
  <a href="https://pypi.org/project/topolab/"><img src="https://img.shields.io/pypi/v/topolab?color=1E3A8A&label=PyPI" alt="PyPI version"></a>
  <a href="https://pypi.org/project/topolab/"><img src="https://img.shields.io/pypi/pyversions/topolab?color=1E3A8A" alt="Python versions"></a>
  <a href="https://github.com/topolab-bv/topolab-python/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/topolab-bv/topolab-python/ci.yml?branch=main&label=CI" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="License: MIT"></a>
  <a href="https://docs.topolab.nl"><img src="https://img.shields.io/badge/docs-topolab.nl-1E3A8A" alt="Documentation"></a>
</p>

<h1 align="center">topolab</h1>

<p align="center">
  The official <b>Python</b> client for the <a href="https://topolab.nl">Topolab</a> dataset and geospatial API.<br>
  Lightweight, GeoJSON-first, sync &amp; async.
</p>

---

## Install

```bash
pip install topolab          # core — GeoJSON-first, minimal dependencies
pip install "topolab[geo]"   # adds GeoPandas for .to_geodataframe()
```

Requires Python 3.10+.

## Quickstart

```python
# Fetch all NL Domino's locations and write to disk
from topolab import Client

tl = Client(api_key="tlb_prod_...")
df = tl.dataset("nl-domino-poi").to_geodataframe()
df.to_file("dominos-nl.geojson")
```

Your API key carries your scope and add-ons — bulk downloads need `API_ACCESS`,
spatial queries need `GIS_ACCESS`, and data routes require an
organization-scoped key. Set `TOPOLAB_API_KEY` in the environment to avoid
hard-coding it:

```python
import os
from topolab import Client

tl = Client(api_key=os.environ["TOPOLAB_API_KEY"])
```

## What you can do

### Browse the catalog

```python
for ds in tl.datasets.list(country="NL", limit=10).data:
    print(ds.table, ds.metadata)
```

### Pull a whole dataset (bulk)

```python
ds = tl.dataset("nl-domino-poi")

fc   = ds.to_geojson()                 # GeoJSON FeatureCollection (a dict)
gdf  = ds.to_geodataframe()            # GeoPandas GeoDataFrame  (needs [geo])
path = ds.download("dominos.geojson")  # streamed to disk, never buffered
```

### Query features in an area (spatial, paged)

```python
fc = tl.dataset("nl-domino-poi").items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])

# or stream every feature, paging transparently:
for feature in tl.dataset("nl-domino-poi").iter_items(page_size=500):
    ...
```

### Async

Every call has an `await`-able mirror on `AsyncClient`:

```python
import asyncio
from topolab import AsyncClient

async def main():
    async with AsyncClient() as tl:               # reads TOPOLAB_API_KEY
        md = await tl.dataset("nl-domino-poi").metadata()
        print(md.table)

asyncio.run(main())
```

## Errors

Every failure raises a subclass of `TopolabError`, so you never parse raw JSON:

| Exception | When |
|---|---|
| `AuthenticationError` | missing or invalid API key (401) |
| `AddonRequiredError` | key lacks the add-on — `.addon` names it (403) |
| `AccessDeniedError` | dataset not accessible to your organization (403) |
| `InsufficientCreditsError` | not enough credits — `.required` / `.available` (402) |
| `NotFoundError` | unknown dataset (404) |
| `RateLimitError` | rate limited — `.retry_after`, retried automatically (429) |

```python
from topolab import Client, AddonRequiredError

try:
    tl.dataset("nl-domino-poi").download("out.geojson")
except AddonRequiredError as e:
    print("Your key needs the add-on:", e.addon)
```

## Documentation

- **Full docs:** [docs.topolab.nl](https://docs.topolab.nl)
- **Two access patterns** (bulk export vs. spatial OGC query), credits, and
  add-ons are explained in the [SDK conventions](https://docs.topolab.nl) and in
  the [`topolab-sdk-spec`](../topolab-sdk-spec) repository.
- A runnable example lives in [`examples/quickstart.py`](examples/quickstart.py).

## Contributing

Issues and pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md).
Run the test suite with `pytest`; build the wheel with `uv build`.

## License

[MIT](LICENSE) © Topolab B.V.
