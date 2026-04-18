from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from shapely.geometry import Point, shape
from shapely.prepared import prep


class ZipPolygon:
    def __init__(self, geojson_path: Path):
        with geojson_path.open() as f:
            feat = json.load(f)
        geom = shape(feat["geometry"])
        self._geom = geom
        self._prepared = prep(geom)
        minx, miny, maxx, maxy = geom.bounds
        self.bbox = {"west": minx, "south": miny, "east": maxx, "north": maxy}

    def contains(self, lon: float, lat: float) -> bool:
        return self._prepared.contains(Point(lon, lat))


def parse_latlon(rec: dict, *keys: str) -> tuple[Optional[float], Optional[float]]:
    """Accepts ('latitude','longitude') or a Socrata point-like dict under a key."""
    if len(keys) == 2:
        lat = rec.get(keys[0])
        lon = rec.get(keys[1])
    elif len(keys) == 1:
        g = rec.get(keys[0])
        if isinstance(g, dict):
            # Socrata "point" type: {"type": "Point", "coordinates": [lon, lat]}
            coords = g.get("coordinates")
            if coords and len(coords) == 2:
                return float(coords[1]), float(coords[0])
            lat = g.get("latitude")
            lon = g.get("longitude")
        else:
            return None, None
    else:
        return None, None
    try:
        return (float(lat), float(lon)) if lat is not None and lon is not None else (None, None)
    except (TypeError, ValueError):
        return None, None
