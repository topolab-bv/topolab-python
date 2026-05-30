import pathlib
import yaml
import topolab
from topolab.dataset import Dataset
from topolab.datasets import DatasetsNamespace

CONV = pathlib.Path(__file__).parents[2] / "topolab-sdk-spec" / "conventions.yaml"


def test_public_surface_matches_conventions():
    conv = yaml.safe_load(CONV.read_text())
    assert hasattr(topolab, "Client") and hasattr(topolab, "AsyncClient")
    py_names = {"dataset", "datasets.list", "metadata", "sample", "to_geojson",
                "download", "to_geodataframe", "items", "iter_items"}
    declared = {m["name"] for m in conv["methods"]}
    assert py_names <= declared
    for m in ["metadata", "sample", "to_geojson", "download", "to_geodataframe", "items", "iter_items"]:
        assert hasattr(Dataset, m), f"Dataset missing {m}"
    assert hasattr(DatasetsNamespace, "list")
    for e in conv["errors"]:
        assert hasattr(topolab, e["name"]), f"missing error {e['name']}"
