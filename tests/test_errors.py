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


# --- code is a string or a number (engine #641) ---
# Bodies are inlined rather than read from topolab-sdk-spec so these tests do
# not depend on fixtures that land in the spec repo separately.

SPENDING_LIMIT = {
    "path": "/v1/dataset/nl-domino-poi/files/geojson", "method": "GET",
    "code": "SPENDING_LIMIT_EXCEEDED",
    "message": "Organization monthly spending limit exceeded",
    "details": {"limit": 5000, "consumed": 4995, "remaining": 5,
                "periodEnd": "2026-11-30T23:59:59.999Z"},
    "time": "2026-11-07T11:52:28.000Z", "requestId": "8f0c41d2",
}

CREDITS = {
    "path": "/v1/dataset/nl-domino-poi/files/geojson", "method": "GET",
    "code": 402, "message": "Insufficient credits",
    "details": {"required": 10, "available": 0},
    "time": "2026-11-07T11:52:28.000Z", "requestId": "6a1b3c5d",
}


def test_string_code_is_kept_and_status_comes_from_the_response():
    err = error_from_response(FakeResp(403, SPENDING_LIMIT))
    # The class still follows the HTTP status; the code refines it.
    assert isinstance(err, AccessDeniedError)
    assert err.code == "SPENDING_LIMIT_EXCEEDED"
    assert isinstance(err.code, str)
    assert err.status == 403
    assert err.status_code == 403
    assert err.details == {"limit": 5000, "consumed": 4995, "remaining": 5,
                           "periodEnd": "2026-11-30T23:59:59.999Z"}
    assert err.request_id == "8f0c41d2"


def test_numeric_code_is_the_status_and_details_are_exposed():
    err = error_from_response(FakeResp(402, CREDITS))
    assert isinstance(err, InsufficientCreditsError)
    assert err.code == 402
    assert isinstance(err.code, int) and not isinstance(err.code, bool)
    assert err.status == 402 == err.status_code
    assert err.details == {"required": 10, "available": 0}
    assert err.required == 10 and err.available == 0


def test_string_code_without_details():
    body = {"code": "SQL_DATA_ERROR", "path": "/v1/sql/query", "method": "POST",
            "message": "The query raised a data error (SQLSTATE 22P02) while evaluating a value."}
    err = error_from_response(FakeResp(400, body))
    assert isinstance(err, ValidationError)
    assert err.code == "SQL_DATA_ERROR"
    assert err.status == 400
    assert err.details is None


@pytest.mark.parametrize("body", [
    {"message": "no code at all"},
    {"code": None, "message": "x"},
    {"code": "", "message": "x"},
    {"code": True, "message": "x"},
    {"code": {"nested": 1}, "message": "x"},
])
def test_code_falls_back_to_the_status(body):
    err = error_from_response(FakeResp(502, body))
    assert isinstance(err, ServerError)
    assert err.code == 502
    assert err.details is None


def test_non_object_details_are_ignored():
    err = error_from_response(FakeResp(403, {"code": 403, "message": "x", "details": ["a"]}))
    assert err.details is None


def test_status_code_alias_is_writable_and_tracks_status():
    err = TopolabError("x", status_code=418)
    assert err.status == 418
    err.status_code = 419
    assert err.status == 419
    err = TopolabError("x", status=420, code="SOME_CODE", details={"a": 1})
    assert err.status_code == 420 and err.code == "SOME_CODE" and err.details == {"a": 1}


def test_client_side_errors_have_no_status_or_code():
    err = ConfigurationError("No API key")
    assert err.status is None and err.status_code is None
    assert err.code is None and err.details is None
