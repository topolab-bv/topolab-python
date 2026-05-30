import pytest
from topolab._geo import to_geodataframe


def test_to_geodataframe_or_skip(fx):
    pytest.importorskip("geopandas")
    gdf = to_geodataframe(fx("full.geojson"))
    assert len(gdf) == 2
    assert gdf.crs.to_epsg() == 4326
