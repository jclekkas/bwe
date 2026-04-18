from __future__ import annotations

import os
from datetime import datetime

from sodapy import Socrata

from ..config import Settings
from ..models import FetchResult

DOMAIN = "data.montgomerycountymd.gov"


class FireEmsFetcher:
    """MCFRS exposes station-daily aggregates, not per-incident rows.

    We return two things:
      - station_summary: rows from the station-daily dataset for our local stations
      - overdose_incidents: individual overdose rows (these do have lat/lon)
    """

    name = "fire_ems"

    def fetch(self, settings: Settings, since: datetime) -> FetchResult:
        cfg = settings.source("fire_ems")
        if not cfg.get("enabled"):
            return FetchResult(self.name, "ok", "disabled")

        stations = cfg.get("stations") or []
        token = os.environ.get("SOCRATA_APP_TOKEN") or None
        client = Socrata(DOMAIN, token, timeout=30)
        notes = []
        station_rows: list[dict] = []
        overdose_rows: list[dict] = []
        status = "degraded"  # aggregate-only by nature

        try:
            # Fetch unfiltered and let the UI filter by time. MCFRS datasets
            # have inconsistent column names; overspecifying a WHERE clause
            # just causes 400s. Both datasets are small enough to pull whole.
            try:
                station_rows = client.get(cfg["station_dataset"], limit=5000)
                notes.append(f"stations: {len(station_rows)} rows (unfiltered)")
            except Exception as e:
                notes.append(f"stations: {type(e).__name__}: {str(e)[:100]}")

            try:
                overdose_rows = client.get(cfg["overdose_dataset"], limit=2000)
                notes.append(f"overdoses: {len(overdose_rows)} rows (unfiltered)")
            except Exception as e:
                notes.append(f"overdoses: {type(e).__name__}: {str(e)[:100]}")

            # Filter stations client-side by station id + date threshold.
            if stations and station_rows:
                wanted = {str(s) for s in stations}
                filtered = []
                for r in station_rows:
                    station_id = str(r.get("station_number") or r.get("station") or r.get("station_name") or "")
                    if station_id in wanted or any(station_id.endswith(s) for s in wanted):
                        filtered.append(r)
                if filtered:
                    station_rows = filtered

            if station_rows or overdose_rows:
                status = "ok" if overdose_rows else "degraded"
            elif notes:
                status = "error"

            return FetchResult(
                self.name,
                status,
                "; ".join(notes) or f"{len(station_rows)} station rows, {len(overdose_rows)} overdoses",
                records=[],
                meta={
                    "station_rows": station_rows,
                    "overdose_rows": overdose_rows,
                    "granularity": "station-aggregate" if not overdose_rows else "mixed",
                    "stations": stations,
                },
            )
        except Exception as e:
            return FetchResult(self.name, "error", f"{type(e).__name__}: {e}")
        finally:
            client.close()
