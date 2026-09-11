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
