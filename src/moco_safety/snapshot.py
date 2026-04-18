from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .config import DATA_DIR, Settings
from .models import FetchResult, Incident, StationSummary
from .normalize import (
    crime_to_incidents,
    dispatched_to_incidents,
    fire_ems_to_outputs,
)

SNAPSHOT_PATH = DATA_DIR / "snapshot.json"
META_PATH = DATA_DIR / "snapshot.meta.json"
HISTORY_DIR = DATA_DIR / "history"


@dataclass
class Snapshot:
    generated_at: str
    zip: str
    window_days: int
    sources: dict[str, Any] = field(default_factory=dict)
    incidents: list[dict] = field(default_factory=list)
    fire_ems_station_summary: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def build_snapshot(
    results: dict[str, FetchResult],
    settings: Settings,
    cat_map: dict[str, str],
) -> Snapshot:
    incidents: list[Incident] = []
    summaries: list[StationSummary] = []

    if "crime" in results:
        incidents.extend(crime_to_incidents(results["crime"], settings, cat_map))
    if "dispatched" in results:
        incidents.extend(dispatched_to_incidents(results["dispatched"], settings))
    if "fire_ems" in results:
        inc, summ = fire_ems_to_outputs(results["fire_ems"], settings)
        incidents.extend(inc)
        summaries.extend(summ)

    sources_meta = {
        name: {
            "status": r.status,
            "note": r.note,
            "count": len(r.records),
            **({"granularity": r.meta["granularity"]} if r.meta.get("granularity") else {}),
        }
        for name, r in results.items()
    }

    return Snapshot(
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        zip=settings.zip,
        window_days=settings.ui_days,
        sources=sources_meta,
        incidents=[i.to_dict() for i in incidents],
        fire_ems_station_summary=[s.to_dict() for s in summaries],
    )


def save(snapshot: Snapshot) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    with SNAPSHOT_PATH.open("w") as f:
        json.dump(snapshot.to_dict(), f, indent=2, sort_keys=True)
    with META_PATH.open("w") as f:
        json.dump(
            {
                "generated_at": snapshot.generated_at,
                "zip": snapshot.zip,
                "sources": snapshot.sources,
                "counts": {
                    "incidents": len(snapshot.incidents),
                    "station_summary": len(snapshot.fire_ems_station_summary),
                },
            },
            f,
            indent=2,
            sort_keys=True,
        )
    # Rotate history
    day = snapshot.generated_at[:10]
    (HISTORY_DIR / f"{day}.json").write_text(json.dumps(snapshot.to_dict(), sort_keys=True))


def prune_history(keep_days: int) -> None:
    if not HISTORY_DIR.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    for p in sorted(HISTORY_DIR.glob("*.json")):
        try:
            d = datetime.fromisoformat(p.stem).replace(tzinfo=timezone.utc)
            if d < cutoff:
                p.unlink()
        except ValueError:
            continue


def load_previous() -> dict | None:
    if not SNAPSHOT_PATH.exists():
        return None
    try:
        return json.loads(SNAPSHOT_PATH.read_text())
    except Exception:
        return None
