import json
import httpx
import pytest
import respx
from topolab import AsyncClient
from topolab.errors import AddonRequiredError

BASE = "https://api.topolab.nl"
COLL = "nl-domino-poi"
TABLE = "business_professional_services_autocrew"


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
        return_value=httpx.Response(403, json={"message": "This endpoint requires the api-access add-on"}))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        with pytest.raises(AddonRequiredError):
            await tl.dataset("nl-domino-poi").download(str("x"))


@respx.mock
async def test_async_iter_owned(fx_owned):
    def page(tables, total, offset):
        return {"items": [{"table": t, "name": t, "links": {}} for t in tables],
                "total": total, "limit": 2, "offset": offset}
    respx.get(f"{BASE}/v1/dataset/owned").mock(side_effect=[
        httpx.Response(200, json=page(["a", "b"], 3, 0)),
        httpx.Response(200, json=page(["c"], 3, 2)),
    ])
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        tables = [d.table async for d in tl.datasets.iter_owned(page_size=2)]
    assert tables == ["a", "b", "c"]


@respx.mock
async def test_async_owned_page(fx_owned):
    respx.get(f"{BASE}/v1/dataset/owned").mock(
        return_value=httpx.Response(200, json=fx_owned("owned.json")))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        page = await tl.datasets.owned(limit=2)
    assert page.total == 193 and len(page.items) == 2


@respx.mock
async def test_async_archives(fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/list").mock(
        return_value=httpx.Response(200, json=fx_owned("archives.json")))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        archives = await tl.dataset(TABLE).archives()
    assert [a.month for a in archives][0] == "2026-07"


@respx.mock
async def test_async_archive_streams_to_disk(tmp_path):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/archives/latest/geojson").mock(
        return_value=httpx.Response(200, content=b"PK\x03\x04zip"))
    out = tmp_path / "a.zip"
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        assert await tl.dataset(TABLE).archive(str(out)) == str(out)
    assert out.read_bytes() == b"PK\x03\x04zip"


async def test_async_archive_rejects_impossible_month(tmp_path):
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        with pytest.raises(ValueError):
            await tl.dataset(TABLE).archive(str(tmp_path / "a.zip"), month="2026-02-29")


@respx.mock
async def test_async_coordinates_reads_headers(fx_owned):
    respx.get(f"{BASE}/v1/dataset/{TABLE}/coordinates").mock(
        return_value=httpx.Response(200, json=fx_owned("coordinates.json"),
                                    headers={"X-Total-Count": "119", "X-Returned-Count": "2",
                                             "X-Offset": "10"}))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        page = await tl.dataset(TABLE).coordinates(limit=2, offset=10)
    assert page.total == 119 and page.returned == 2 and page.offset == 10
    assert page.rows[0].latitude == "51.49638600"


@respx.mock
async def test_async_sql(fx_owned):
    route = respx.post(f"{BASE}/v1/sql/query").mock(
        return_value=httpx.Response(200, json=fx_owned("sql-result.json")))
    async with AsyncClient(api_key="k", base_url=BASE) as tl:
        res = await tl.sql("SELECT 1", max_rows=5)
    assert res.rowCount == 2
    assert json.loads(route.calls.last.request.content) == {"sql": "SELECT 1", "maxRows": 5}
