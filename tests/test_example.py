import pathlib
import httpx
import respx
import pytest

BASE = "https://api.topolab.nl"
EX = pathlib.Path(__file__).parents[2] / "topolab-sdk-spec" / "examples" / "example.py"


@respx.mock
def test_advertised_example_executes(fx, tmp_path):
    pytest.importorskip("geopandas")
    respx.get(f"{BASE}/v1/dataset/nl-domino-poi/files/geojson").mock(
        return_value=httpx.Response(200, json=fx("full.geojson")))
    code = EX.read_text().replace('api_key="tlb_prod_..."', 'api_key="k", base_url="%s"' % BASE)
    code = code.replace('"dominos-nl.geojson"', repr(str(tmp_path / "out.geojson")))
    exec(compile(code, str(EX), "exec"), {})
    assert (tmp_path / "out.geojson").exists()
