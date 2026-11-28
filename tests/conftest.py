import json
import pathlib
import pytest

FIXTURES = pathlib.Path(__file__).parents[2] / "topolab-sdk-spec" / "fixtures"
FIX = FIXTURES / "nl-domino-poi"


@pytest.fixture
def fx():
    def load(name):
        return json.loads((FIX / name).read_text())
    return load


@pytest.fixture
def fx_owned():
    def load(name):
        return json.loads((FIXTURES / "owned" / name).read_text())
    return load


@pytest.fixture
def no_link_route():
    """Make the mocked server answer the link route as a server without it does.

    Staging answered `POST /v1/dataset/<table>/exports` with this 404 on
    2026-11-24. download() and archive() then fall back to the old routes, so
    the tests that pin the old routes' behaviour register this first.
    """
    import httpx
    import respx

    def register(base: str, table: str):
        return respx.post(f"{base}/v1/dataset/{table}/exports").mock(return_value=httpx.Response(
            404, json={"path": f"/v1/dataset/{table}/exports", "method": "POST", "code": 404,
                       "message": f"Cannot POST /v1/dataset/{table}/exports",
                       "time": "2026-11-23T23:43:35.228Z",
                       "requestId": "2b12c5708156347fdeffee2d7be873a7"}))
    return register
