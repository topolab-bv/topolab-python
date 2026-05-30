import httpx
import respx
import pytest
from topolab._transport import Transport
from topolab.errors import RateLimitError, AddonRequiredError

BASE = "https://api.topolab.nl"


def make() -> Transport:
    return Transport(api_key="tlb_test_x", base_url=BASE, max_retries=2, _backoff_base=0)


@respx.mock
def test_sets_api_key_and_user_agent():
    route = respx.get(f"{BASE}/v1/dataset/all").mock(
        return_value=httpx.Response(200, json={"data": [], "meta": {}}))
    make().get_json("/v1/dataset/all")
    req = route.calls.last.request
    assert req.headers["x-api-key"] == "tlb_test_x"
    assert req.headers["user-agent"].startswith("topolab-python/")


@respx.mock
def test_retries_on_429_then_succeeds():
    route = respx.get(f"{BASE}/v1/dataset/all").mock(side_effect=[
        httpx.Response(429, json={"message": "rl", "retryAfter": 0}),
        httpx.Response(200, json={"data": [], "meta": {}}),
    ])
    out = make().get_json("/v1/dataset/all")
    assert out == {"data": [], "meta": {}}
    assert route.call_count == 2


@respx.mock
def test_raises_after_retries_exhausted():
    respx.get(f"{BASE}/v1/dataset/all").mock(
        return_value=httpx.Response(429, json={"message": "rl", "retryAfter": 0}))
    with pytest.raises(RateLimitError):
        make().get_json("/v1/dataset/all")


@respx.mock
def test_403_not_retried_and_typed():
    route = respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(403, json={"message": "This endpoint requires the API_ACCESS add-on"}))
    with pytest.raises(AddonRequiredError):
        make().get_json("/v1/dataset/nl-domino-poi/files/geojson")
    assert route.call_count == 1
