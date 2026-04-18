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

    Actual Socrata columns (verified against the live schema):
      incident_id, cr_number, crash_reports, start_time, end_time, priority,
      initial_type, close_type, address, city, state, zip, longitude, latitude,
      police_district_number, sector, pra, calltime_*, disposition_desc, geolocation.

    We filter by bbox on geolocation, then optionally filter by the ZIP polygon
    client-side.
    """

    name = "dispatched"

    def fetch(self, settings: Settings, since: datetime) -> FetchResult:
        cfg = settings.source("dispatched")
        if not cfg.get("enabled"):
            return FetchResult(self.name, "ok", "disabled")

        bb = settings.bbox
        token = os.environ.get("SOCRATA_APP_TOKEN") or None
        client = Socrata(DOMAIN, token, timeout=60)
        try:
            since_str = since.strftime("%Y-%m-%dT%H:%M:%S")
            # Try zip-based filter first (fastest, exact); fall back to bbox.
            attempts = [
                f"zip='{settings.zip}' AND start_time >= '{since_str}'",
                (
                    f"within_box(geolocation, {bb['north']}, {bb['west']}, {bb['south']}, {bb['east']})"
                    f" AND start_time >= '{since_str}'"
                ),
                (
                    f"latitude between {bb['south']} and {bb['north']}"
                    f" AND longitude between {bb['west']} and {bb['east']}"
                    f" AND start_time >= '{since_str}'"
                ),
            ]
            rows: list[dict] = []
            used = ""
            last_err: Exception | None = None
            for where in attempts:
                try:
                    rows = client.get(
                        cfg["dataset"],
                        where=where,
                        order="start_time DESC",
                        limit=10000,
                    )
                    used = where
                    break
                except Exception as e:
                    last_err = e
                    continue
            if not used and last_err is not None:
                return FetchResult(self.name, "error", f"all filters failed: {type(last_err).__name__}: {last_err}")

            # Client-side polygon filter to drop bbox false positives.
            poly = ZipPolygon(CONFIG_DIR / f"zip_{settings.zip}.geojson")
            filtered = []
            for r in rows:
                if (r.get("zip") or "").strip() == settings.zip:
                    filtered.append(r)
                    continue
                lat, lon = parse_latlon(r, "geolocation")
                if lat is None:
                    lat, lon = parse_latlon(r, "latitude", "longitude")
                if lat is None or lon is None:
                    continue
                if poly.contains(lon, lat):
                    filtered.append(r)

            # Dedupe on (initial_type, address, minute).
            seen: set[tuple] = set()
            deduped = []
            for r in filtered:
                key = (
                    r.get("initial_type") or r.get("close_type") or "",
                    r.get("address") or "",
                    (r.get("start_time") or "")[:16],
                )
                if key in seen:
                    continue
                seen.add(key)
                deduped.append(r)

            return FetchResult(
                self.name,
                "ok",
                f"{len(rows)} raw, {len(filtered)} in ZIP, {len(deduped)} after dedupe (filter: {used[:60]}...)",
                records=deduped,
                meta={"dataset": cfg["dataset"], "bbox": bb},
            )
        except Exception as e:
            return FetchResult(self.name, "error", f"{type(e).__name__}: {e}")
        finally:
            client.close()
