import json
import pathlib
import pytest

FIX = pathlib.Path(__file__).parents[2] / "topolab-sdk-spec" / "fixtures" / "nl-domino-poi"


@pytest.fixture
def fx():
    def load(name):
        return json.loads((FIX / name).read_text())
    return load
