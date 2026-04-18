from __future__ import annotations

import os
from datetime import datetime

from sodapy import Socrata

from ..config import Settings
from ..models import FetchResult

DOMAIN = "data.montgomerycountymd.gov"


class CrimeFetcher:
    name = "crime"

    def fetch(self, settings: Settings, since: datetime) -> FetchResult:
        cfg = settings.source("crime")
        if not cfg.get("enabled"):
            return FetchResult(self.name, "ok", "disabled")

        token = os.environ.get("SOCRATA_APP_TOKEN") or None
        client = Socrata(DOMAIN, token, timeout=30)
        try:
            where = f"zip_code='{settings.zip}' AND start_date >= '{since.strftime('%Y-%m-%dT%H:%M:%S')}'"
            rows = client.get(
                cfg["dataset"],
                where=where,
                order="start_date DESC",
                limit=5000,
            )
            return FetchResult(
                self.name,
                "ok",
                f"fetched {len(rows)} rows",
                records=rows,
                meta={"dataset": cfg["dataset"], "where": where},
            )
        except Exception as e:
            return FetchResult(self.name, "error", f"{type(e).__name__}: {e}")
        finally:
            client.close()
