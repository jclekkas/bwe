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
            if stations:
                station_list = ", ".join(str(s) for s in stations)
                station_date = since.strftime("%Y-%m-%d")
                # Try a few column-name variants since MoCo datasets vary.
                station_attempts = [
                    f"station_number in({station_list}) AND date >= '{station_date}'",
                    f"station in({station_list}) AND date >= '{station_date}'",
                    f"station_number in({station_list})",
                    f"station in({station_list})",
                ]
                for where in station_attempts:
                    try:
                        station_rows = client.get(
                            cfg["station_dataset"],
                            where=where,
                            limit=5000,
                        )
                        notes.append(f"stations via: {where[:40]}...")
                        break
                    except Exception as e:
                        notes.append(f"stations try: {type(e).__name__}: {str(e)[:80]}")
                        continue

            since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
            overdose_attempts = [
                f"incident_date_time >= '{since_iso}'",
                f"date >= '{since_iso}'",
                f"incident_date >= '{since.strftime('%Y-%m-%d')}'",
                None,  # unfiltered, let the normalizer handle date parsing
            ]
            for where in overdose_attempts:
                try:
                    if where is None:
                        overdose_rows = client.get(cfg["overdose_dataset"], limit=2000)
                    else:
                        overdose_rows = client.get(
                            cfg["overdose_dataset"],
                            where=where,
                            limit=2000,
                        )
                    notes.append(f"overdoses via: {where or 'no filter'}")
                    break
                except Exception as e:
                    notes.append(f"overdoses try: {type(e).__name__}: {str(e)[:80]}")
                    continue

            if not station_rows and not overdose_rows and notes:
                status = "error"
            else:
                status = "degraded" if not overdose_rows else "ok"

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
