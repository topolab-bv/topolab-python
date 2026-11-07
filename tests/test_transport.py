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
        return_value=httpx.Response(403, json={"message": "This endpoint requires the api-access add-on"}))
    with pytest.raises(AddonRequiredError):
        make().get_json("/v1/dataset/nl-domino-poi/files/geojson")
    assert route.call_count == 1


def test_delay_uses_the_retry_after_header_then_details_then_the_legacy_body():
    t = make()
    rate = {"code": "RATE_LIMIT_EXCEEDED", "message": "x", "details": {"retryAfter": 7}}
    assert t._delay(0, httpx.Response(429, json=rate, headers={"retry-after": "9"})) == 9
    assert t._delay(0, httpx.Response(429, json=rate)) == 7
    assert t._delay(0, httpx.Response(429, json={"message": "x", "retryAfter": 5})) == 5
    # Nothing to go on: exponential backoff (base 0 here).
    assert t._delay(0, httpx.Response(429, json={"code": "USAGE_QUOTA_EXCEEDED", "message": "x",
                                                 "details": {"quota": 1, "used": 1}})) == 0


@respx.mock
def test_retries_a_rate_limit_429_with_details_then_succeeds():
    route = respx.get(f"{BASE}/v1/dataset/all").mock(side_effect=[
        httpx.Response(429, json={"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded",
                                  "details": {"retryAfter": 0, "limit": 60, "remaining": 0,
                                              "resetAt": "2026-11-07T12:01:00.000Z"}}),
        httpx.Response(200, json={"data": [], "meta": {}}),
    ])
    make().get_json("/v1/dataset/all")
    assert route.call_count == 2
