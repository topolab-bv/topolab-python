import httpx
import respx
from topolab import AsyncClient

BASE = "https://api.topolab.nl"
COLL = "dataset-3f9a2c7e-8b1d-4056-a1c2-e3f4a5b6c7d8"


@respx.mock
async def test_async_metadata(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi").mock(
        return_value=httpx.Response(200, json=fx("metadata.json")))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        md = await tl.dataset("nl-domino-poi").metadata()
    assert md.table == "nl-domino-poi"


@respx.mock
async def test_async_iter_items(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi").mock(
        return_value=httpx.Response(200, json=fx("metadata.json")))
    respx.get(f"{BASE}/v1/ogc/collections/{COLL}/items").mock(side_effect=[
        httpx.Response(200, json=fx("items.json")),
        httpx.Response(200, json={"type": "FeatureCollection", "features": []}),
    ])
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        feats = [f async for f in tl.dataset("nl-domino-poi").iter_items(page_size=2)]
    assert len(feats) == 2
