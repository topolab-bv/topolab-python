import json
import pathlib
import pytest
from topolab.errors import (
    TopolabError, AuthenticationError, AddonRequiredError, AccessDeniedError,
    InsufficientCreditsError, NotFoundError, ConfigurationError, QueryTimeoutError,
    RateLimitError, ValidationError, ServerError, error_from_response,
)

FIXTURES = pathlib.Path(__file__).parents[2] / "topolab-sdk-spec" / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text())


class FakeResp:
    def __init__(self, status_code, json_body, headers=None):
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}

    def json(self):
        return self._json


@pytest.mark.parametrize("fixture_name,addon", [
    ("nl-domino-poi/error-403-addon.json", "api-access"),
    ("nl-domino-poi/error-403-addon-archive.json", "archived-data"),
])
def test_403_addon_maps_to_addon_required_and_names_addon(fixture_name, addon):
    # Both real message shapes — the slug form and the prose form — normalise to
    # the same hyphenated add-on identifier.
    err = error_from_response(FakeResp(403, fixture(fixture_name)))
    assert isinstance(err, AddonRequiredError)
    assert err.addon == addon


def test_403_access_maps_to_access_denied():
    err = error_from_response(FakeResp(403, {"message": "Organization does not have access to this dataset"}))
    assert isinstance(err, AccessDeniedError)


def test_402_credits_carries_required_available():
    err = error_from_response(FakeResp(402, {"message": "Insufficient credits", "details": {"required": 10, "available": 0}}))
    assert isinstance(err, InsufficientCreditsError)
    assert err.required == 10 and err.available == 0


def test_429_carries_retry_after_from_body():
    err = error_from_response(FakeResp(429, {"message": "Rate limit exceeded", "retryAfter": 2}))
    assert isinstance(err, RateLimitError)
    assert err.retry_after == 2


def test_401_and_404_and_400():
    assert isinstance(error_from_response(FakeResp(401, {"message": "x"})), AuthenticationError)
    assert isinstance(error_from_response(FakeResp(404, {"message": "x"})), NotFoundError)
    assert isinstance(error_from_response(FakeResp(400, {"message": "organization"})), ConfigurationError)


def test_408_maps_to_query_timeout():
    err = error_from_response(FakeResp(408, {"code": 408, "message": "Query exceeded the time limit"}))
    assert isinstance(err, QueryTimeoutError)


def test_request_id_falls_back_to_the_body():
    # The envelope has no statusCode; requestId is the only id when the
    # X-Request-Id header is absent.
    body = fixture("owned/error-400-month.json")
    err = error_from_response(FakeResp(400, body))
    assert isinstance(err, ValidationError)
    assert "statusCode" not in body
    assert err.request_id == body["requestId"]
    assert err.status_code == 400


def test_request_id_header_wins_over_the_body():
    err = error_from_response(FakeResp(400, {"message": "x", "requestId": "body"},
                                       headers={"x-request-id": "header"}))
    assert err.request_id == "header"


def test_all_subclasses_inherit_base():
    for e in [AuthenticationError, RateLimitError, ServerError]:
        assert issubclass(e, TopolabError)
