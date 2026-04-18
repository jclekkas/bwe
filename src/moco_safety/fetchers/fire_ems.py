from __future__ import annotations

import os
from datetime import datetime

from sodapy import Socrata

from ..config import Settings
from ..models import FetchResult

DOMAIN = "data.montgomerycountymd.gov"


class FireEmsFetcher:
    """MCFRS station dataset is per-incident. Real columns (observed 2026-04-18):
    fire_station, fire_station_number, incident_number, call_type_description,
    date, time, location, station_address.

    We return:
      - station_rows: per-incident rows for our local stations
      - overdose_rows: individual overdose incidents (lat/lon present)
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
                sample_keys = sorted(station_rows[0].keys()) if station_rows else []
                notes.append(f"stations: {len(station_rows)} rows; columns={sample_keys}")
            except Exception as e:
                notes.append(f"stations: {type(e).__name__}: {str(e)[:100]}")

            try:
                overdose_rows = client.get(cfg["overdose_dataset"], limit=2000)
                sample_keys = sorted(overdose_rows[0].keys()) if overdose_rows else []
                notes.append(f"overdoses: {len(overdose_rows)} rows; columns={sample_keys}")
            except Exception as e:
                notes.append(f"overdoses: {type(e).__name__}: {str(e)[:100]}")

            # Per-incident rows. Match station by fire_station_number (canonical,
            # observed in the live data). Fall back to fire_station text match
            # for completeness.
            if stations and station_rows:
                wanted = {str(s) for s in stations}
                filtered = []
                for r in station_rows:
                    num = str(r.get("fire_station_number") or "").strip()
                    txt = str(r.get("fire_station") or "").strip()
                    if num in wanted or any(txt.endswith(f" {s}") or txt == f"Station {s}" for s in wanted):
                        filtered.append(r)
                station_rows = filtered
                notes.append(f"stations filtered to {len(filtered)} rows for fire_station_number in {sorted(wanted)}")

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
                    "granularity": "per-incident",
                    "stations": stations,
                },
            )
        except Exception as e:
            return FetchResult(self.name, "error", f"{type(e).__name__}: {e}")
        finally:
            client.close()
