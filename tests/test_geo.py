from moco_safety.config import CONFIG_DIR
from moco_safety.util.geo import ZipPolygon, parse_latlon


def test_zip_polygon_contains_center():
    p = ZipPolygon(CONFIG_DIR / "zip_20874.geojson")
    assert p.contains(-77.24, 39.17) is True
    assert p.contains(-76.6, 39.29) is False  # Baltimore area


def test_parse_latlon_pair():
    lat, lon = parse_latlon({"latitude": "39.1", "longitude": "-77.2"}, "latitude", "longitude")
    assert (lat, lon) == (39.1, -77.2)


def test_parse_latlon_point_dict():
    lat, lon = parse_latlon(
        {"location": {"type": "Point", "coordinates": [-77.2, 39.1]}}, "location"
    )
    assert (lat, lon) == (39.1, -77.2)


def test_parse_latlon_missing():
    assert parse_latlon({}, "latitude", "longitude") == (None, None)
