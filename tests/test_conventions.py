import pathlib
import yaml
import topolab
from topolab.client import Client
from topolab.dataset import Dataset
from topolab.datasets import DatasetsNamespace
from topolab.async_client import AsyncClient, AsyncDataset, AsyncDatasetsNamespace

CONV = pathlib.Path(__file__).parents[2] / "topolab-sdk-spec" / "conventions.yaml"

DATASET_METHODS = ["metadata", "sample", "to_geojson", "download", "to_geodataframe",
                   "items", "iter_items", "archives", "archive", "coordinates"]
NAMESPACE_METHODS = ["list", "owned", "iter_owned"]
CLIENT_METHODS = ["dataset", "sql"]


def test_public_surface_matches_conventions():
    conv = yaml.safe_load(CONV.read_text())
    assert hasattr(topolab, "Client") and hasattr(topolab, "AsyncClient")
    py_names = {"dataset", "datasets.list", "metadata", "sample", "to_geojson",
                "download", "to_geodataframe", "items", "iter_items",
                "datasets.owned", "iter_owned", "archives", "archive",
                "coordinates", "sql"}
    declared = {m["name"] for m in conv["methods"]}
    assert py_names <= declared
    for m in DATASET_METHODS:
        assert hasattr(Dataset, m), f"Dataset missing {m}"
    for m in NAMESPACE_METHODS:
        assert hasattr(DatasetsNamespace, m), f"DatasetsNamespace missing {m}"
    for m in CLIENT_METHODS:
        assert hasattr(Client, m), f"Client missing {m}"
    for e in conv["errors"]:
        assert hasattr(topolab, e["name"]), f"missing error {e['name']}"


def test_async_surface_mirrors_sync():
    for m in DATASET_METHODS:
        assert hasattr(AsyncDataset, m), f"AsyncDataset missing {m}"
    for m in NAMESPACE_METHODS:
        assert hasattr(AsyncDatasetsNamespace, m), f"AsyncDatasetsNamespace missing {m}"
    for m in CLIENT_METHODS:
        assert hasattr(AsyncClient, m), f"AsyncClient missing {m}"
