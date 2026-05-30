import httpx
import respx
import pytest
from topolab import Client
from topolab.errors import ConfigurationError

BASE = "https://api.topolab.nl"


@respx.mock
def test_catalog_list(fx):
    respx.get(f"{BASE}/v1/dataset/all").mock(
        return_value=httpx.Response(200, json=fx("catalog.json")))
    page = Client(api_key="k", base_url=BASE).datasets.list(limit=20)
    assert page.meta.totalItems == 1
    assert page.data[0].table == "nl-domino-poi"


def test_api_key_from_env(monkeypatch):
    monkeypatch.setenv("TOPOLAB_API_KEY", "tlb_env_key")
    assert Client().api_key == "tlb_env_key"


def test_missing_key_raises(monkeypatch):
    monkeypatch.delenv("TOPOLAB_API_KEY", raising=False)
    with pytest.raises(ConfigurationError):
        Client(api_key=None, base_url=BASE)


def test_default_environment_is_production(monkeypatch):
    monkeypatch.delenv("TOPOLAB_BASE_URL", raising=False)
    monkeypatch.delenv("TOPOLAB_ENV", raising=False)
    assert Client(api_key="k").base_url == "https://api.topolab.nl"


def test_environment_staging(monkeypatch):
    monkeypatch.delenv("TOPOLAB_BASE_URL", raising=False)
    monkeypatch.delenv("TOPOLAB_ENV", raising=False)
    assert Client(api_key="k", environment="staging").base_url == "https://api-staging.topolab.nl"


def test_unknown_environment_raises():
    with pytest.raises(ConfigurationError):
        Client(api_key="k", environment="dev")


def test_topolab_env_var(monkeypatch):
    monkeypatch.delenv("TOPOLAB_BASE_URL", raising=False)
    monkeypatch.setenv("TOPOLAB_ENV", "staging")
    assert Client(api_key="k").base_url == "https://api-staging.topolab.nl"


def test_base_url_beats_environment(monkeypatch):
    monkeypatch.delenv("TOPOLAB_BASE_URL", raising=False)
    monkeypatch.delenv("TOPOLAB_ENV", raising=False)
    # explicit base_url wins over environment
    c = Client(api_key="k", base_url="https://self.example/api", environment="staging")
    assert c.base_url == "https://self.example/api"


def test_async_environment_staging(monkeypatch):
    from topolab import AsyncClient
    monkeypatch.delenv("TOPOLAB_BASE_URL", raising=False)
    monkeypatch.delenv("TOPOLAB_ENV", raising=False)
    assert AsyncClient(api_key="k", environment="staging").base_url == "https://api-staging.topolab.nl"


def test_base_url_rejects_plain_http_remote():
    with pytest.raises(ConfigurationError):
        Client(api_key="k", base_url="http://evil.example/api")


def test_base_url_rejects_userinfo():
    with pytest.raises(ConfigurationError):
        Client(api_key="k", base_url="https://user:pass@evil.example")


def test_base_url_rejects_non_http_scheme():
    with pytest.raises(ConfigurationError):
        Client(api_key="k", base_url="ftp://api.topolab.nl")


def test_base_url_allows_loopback_http():
    assert Client(api_key="k", base_url="http://127.0.0.1:8080").base_url == "http://127.0.0.1:8080"


def test_topolab_base_url_env_is_validated(monkeypatch):
    monkeypatch.setenv("TOPOLAB_BASE_URL", "http://evil.example")
    with pytest.raises(ConfigurationError):
        Client(api_key="k")
