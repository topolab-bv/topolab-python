"""Optional geopandas conversion. Requires ``pip install topolab[geo]``."""
from __future__ import annotations


def to_geodataframe(feature_collection: dict):
    try:
        import geopandas as gpd
    except ImportError as e:
        raise ImportError(
            'to_geodataframe() needs geopandas. Install with: pip install "topolab[geo]"'
        ) from e
    return gpd.GeoDataFrame.from_features(
        feature_collection.get("features", []), crs="EPSG:4326")
