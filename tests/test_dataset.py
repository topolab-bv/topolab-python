import httpx
import respx
import pytest
from topolab import Client
from topolab.errors import AddonRequiredError

BASE = "https://api.topolab.nl"
# The OGC collectionId is the dataset slug (no slug->uuid resolution).
COLL = "nl-domino-poi"


@respx.mock
def test_metadata(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi").mock(
        return_value=httpx.Response(200, json=fx("metadata.json")))
    md = Client(api_key="k", base_url=BASE).dataset("nl-domino-poi").metadata()
    assert md.id == "3f9a2c7e-8b1d-4056-a1c2-e3f4a5b6c7d8"
    assert md.table == "nl-domino-poi"


@respx.mock
def test_to_geojson_returns_feature_collection(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(200, json=fx("full.geojson"),
                                    headers={"content-type": "application/geo+json"}))
    fc = Client(api_key="k", base_url=BASE).dataset("nl-domino-poi").to_geojson()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 2


@respx.mock
def test_items_uses_slug_directly(fx):
    md = respx.get(f"{BASE}/v1/dataset/nl-domino-poi").mock(
        return_value=httpx.Response(200, json=fx("metadata.json")))
    items = respx.get(f"{BASE}/v1/ogc/collections/{COLL}/items").mock(
        return_value=httpx.Response(200, json=fx("items.json")))
    ds = Client(api_key="k", base_url=BASE).dataset("nl-domino-poi")
    fc1 = ds.items(limit=100, bbox=[4.7, 52.2, 5.1, 52.5])
    ds.items(limit=10)
    assert fc1["type"] == "FeatureCollection"
    assert md.call_count == 0          # collectionId IS the slug — no metadata round-trip
    assert items.call_count == 2
    assert items.calls[0].request.url.params["bbox"] == "4.7,52.2,5.1,52.5"


@respx.mock
def test_addon_error_on_download(fx):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(403, json={"message": "This endpoint requires the API_ACCESS add-on"}))
    with pytest.raises(AddonRequiredError):
        Client(api_key="k", base_url=BASE).dataset("nl-domino-poi").to_geojson()


@respx.mock
def test_iter_items_paginates(fx):
    respx.get(f"{BASE}/v1/ogc/collections/{COLL}/items").mock(side_effect=[
        httpx.Response(200, json=fx("items.json")),                          # 2 features
        httpx.Response(200, json={"type": "FeatureCollection", "features": []}),  # stop
    ])
    feats = list(Client(api_key="k", base_url=BASE).dataset("nl-domino-poi").iter_items(page_size=2))
    assert len(feats) == 2


@respx.mock
def test_download_streams_to_disk(fx, tmp_path):
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(200, json=fx("full.geojson")))
    out = tmp_path / "out.geojson"
    Client(api_key="k", base_url=BASE).dataset("nl-domino-poi").download(str(out))
    assert out.exists()
    import json
    assert json.loads(out.read_text())["type"] == "FeatureCollection"
