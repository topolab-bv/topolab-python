import json
import httpx
import pytest
import respx
from topolab import AsyncClient
from topolab.errors import AddonRequiredError

BASE = "https://api.topolab.nl"
COLL = "nl-domino-poi"


@respx.mock
async def test_async_metadata(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi").mock(
        return_value=httpx.Response(200, json=fx("metadata.json")))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        md = await tl.dataset("nl-domino-poi").metadata()
    assert md.table == "nl-domino-poi"


@respx.mock
async def test_async_iter_items(fx):
    respx.get(f"{BASE}/v1/ogc/collections/{COLL}/items").mock(side_effect=[
        httpx.Response(200, json=fx("items.json")),
        httpx.Response(200, json={"type": "FeatureCollection", "features": []}),
    ])
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        feats = [f async for f in tl.dataset("nl-domino-poi").iter_items(page_size=2)]
    assert len(feats) == 2


@respx.mock
async def test_async_items_slug_direct(fx):
    md = respx.get(f"{BASE}/v1/dataset/nl-domino-poi").mock(
        return_value=httpx.Response(200, json=fx("metadata.json")))
    respx.get(f"{BASE}/v1/ogc/collections/{COLL}/items").mock(
        return_value=httpx.Response(200, json=fx("items.json")))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        fc = await tl.dataset("nl-domino-poi").items(limit=10)
    assert fc["type"] == "FeatureCollection"
    assert md.call_count == 0  # collectionId IS the slug — no metadata round-trip


@respx.mock
async def test_async_sample(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/sample/geojson").mock(
        return_value=httpx.Response(200, json=fx("items.json"),
                                    headers={"content-type": "application/geo+json"}))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        s = await tl.dataset("nl-domino-poi").sample("geojson")
    assert s["type"] == "FeatureCollection"


async def test_async_sample_rejects_unknown_format():
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        with pytest.raises(ValueError):
            await tl.dataset("nl-domino-poi").sample("xlsx")


@respx.mock
async def test_async_download_streams_to_disk(fx, tmp_path):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(200, json=fx("full.geojson")))
    out = tmp_path / "out.geojson"
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        await tl.dataset("nl-domino-poi").download(str(out))
    assert out.exists()
    assert json.loads(out.read_text())["type"] == "FeatureCollection"


@respx.mock
async def test_async_download_addon_error():
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(403, json={"message": "This endpoint requires the API_ACCESS add-on"}))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        with pytest.raises(AddonRequiredError):
            await tl.dataset("nl-domino-poi").download(str("x"))
