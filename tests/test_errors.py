import pytest
from topolab.errors import (
    TopolabError, AuthenticationError, AddonRequiredError, AccessDeniedError,
    InsufficientCreditsError, NotFoundError, ConfigurationError, RateLimitError,
    ValidationError, ServerError, error_from_response,
)


class FakeResp:
    def __init__(self, status_code, json_body, headers=None):
        self.status_code = status_code
        self._json = json_body
        self.headers = headers or {}

    def json(self):
        return self._json


def test_403_addon_maps_to_addon_required_and_names_addon():
    err = error_from_response(FakeResp(403, {"message": "This endpoint requires the API_ACCESS add-on"}))
    assert isinstance(err, AddonRequiredError)
    assert err.addon == "API_ACCESS"


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


def test_all_subclasses_inherit_base():
    for e in [AuthenticationError, RateLimitError, ServerError]:
        assert issubclass(e, TopolabError)
