from __future__ import annotations

import os
from datetime import datetime

from sodapy import Socrata

from ..config import CONFIG_DIR, Settings
from ..models import FetchResult
from ..util.geo import ZipPolygon, parse_latlon

DOMAIN = "data.montgomerycountymd.gov"


class DispatchedFetcher:
    """MoCo Police Dispatched Incidents (98cc-bc7d).

    No reliable zip_code field, so we filter geographically: bbox via SoQL,
    then point-in-polygon client-side to drop false positives.
    """

    name = "dispatched"

    def fetch(self, settings: Settings, since: datetime) -> FetchResult:
        cfg = settings.source("dispatched")
        if not cfg.get("enabled"):
            return FetchResult(self.name, "ok", "disabled")

        bb = settings.bbox
        token = os.environ.get("SOCRATA_APP_TOKEN") or None
        client = Socrata(DOMAIN, token, timeout=30)
        try:
            # within_box(location, NW_lat, NW_lon, SE_lat, SE_lon)
            where = (
                f"within_box(location, {bb['north']}, {bb['west']}, {bb['south']}, {bb['east']})"
                f" AND start_date_time >= '{since.strftime('%Y-%m-%dT%H:%M:%S')}'"
            )
            try:
                rows = client.get(
                    cfg["dataset"],
                    where=where,
                    order="start_date_time DESC",
                    limit=10000,
                )
            except Exception:
                # Some datasets use a differently named geo column; fall back to lat/lon bbox.
                where = (
                    f"latitude between {bb['south']} and {bb['north']}"
                    f" AND longitude between {bb['west']} and {bb['east']}"
                    f" AND start_date_time >= '{since.strftime('%Y-%m-%dT%H:%M:%S')}'"
                )
                rows = client.get(
                    cfg["dataset"],
                    where=where,
                    order="start_date_time DESC",
                    limit=10000,
                )

            poly = ZipPolygon(CONFIG_DIR / f"zip_{settings.zip}.geojson")
            filtered = []
            for r in rows:
                lat, lon = parse_latlon(r, "location")
                if lat is None:
                    lat, lon = parse_latlon(r, "latitude", "longitude")
                if lat is None or lon is None:
                    continue
                if poly.contains(lon, lat):
                    filtered.append(r)

            # Dedupe on (incident_type, address, minute).
            seen: set[tuple] = set()
            deduped = []
            for r in filtered:
                key = (
                    r.get("incident_type") or r.get("description") or "",
                    r.get("location_address") or r.get("address") or "",
                    (r.get("start_date_time") or "")[:16],
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(r)

            return FetchResult(
                self.name,
                "ok",
                f"{len(rows)} raw, {len(filtered)} in ZIP, {len(deduped)} after dedupe",
                records=deduped,
                meta={"dataset": cfg["dataset"], "bbox": bb},
            )
        except Exception as e:
            return FetchResult(self.name, "error", f"{type(e).__name__}: {e}")
        finally:
            client.close()
