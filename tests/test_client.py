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
