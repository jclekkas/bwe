from __future__ import annotations

from typing import Optional

from .config import Settings
from .models import FetchResult, Incident, StationSummary
from .util.geo import parse_latlon


def _category(crimename1: str | None, cat_map: dict[str, str]) -> str:
    if not crimename1:
        return "Other"
    return cat_map.get(crimename1.lower(), "Other")


def _nonnull(s: Optional[str]) -> str:
    return (s or "").strip()


def _row_url(base: str, row_id: str | None) -> str:
    if not row_id:
        return base
    return f"{base}/row-{row_id}"


def crime_to_incidents(r: FetchResult, settings: Settings, cat_map: dict[str, str]) -> list[Incident]:
    out: list[Incident] = []
    base = settings.source("crime").get("row_url", "")
    for rec in r.records:
        lat, lon = parse_latlon(rec, "latitude", "longitude")
        if lat is None:
            lat, lon = parse_latlon(rec, "location")
        name1 = rec.get("crimename1") or rec.get("offense")
        name2 = rec.get("crimename2") or ""
        name3 = rec.get("crimename3") or ""
        desc = name3 or name2 or name1 or "Crime incident"
        incident_id = str(
            rec.get("incident_id") or rec.get(":id") or rec.get("cr_number") or f"c-{len(out)}"
        )
        out.append(Incident(
            id=f"crime-{incident_id}",
            source="crime",
            category=_category(name1, cat_map),
            subcategory=_nonnull(name2),
            description=_nonnull(desc),
            occurred_at=rec.get("start_date"),
            reported_at=rec.get("end_date"),
            lat=lat,
            lon=lon,
            address=_nonnull(rec.get("address") or rec.get("block_address")),
            zip_code=_nonnull(rec.get("zip_code")) or settings.zip,
            raw_url=_row_url(base, incident_id),
            raw=rec,
        ))
    return out


def dispatched_to_incidents(r: FetchResult, settings: Settings) -> list[Incident]:
    out: list[Incident] = []
    base = settings.source("dispatched").get("row_url", "")
    for rec in r.records:
        lat, lon = parse_latlon(rec, "latitude", "longitude")
        if lat is None:
            lat, lon = parse_latlon(rec, "geolocation")
        desc = (
            rec.get("initial_type")
            or rec.get("close_type")
            or rec.get("disposition_desc")
            or rec.get("incident_type")
            or "Dispatched call"
        )
        incident_id = str(
            rec.get("incident_id") or rec.get(":id") or rec.get("cr_number") or f"d-{len(out)}"
        )
        out.append(Incident(
            id=f"dispatched-{incident_id}",
            source="dispatched",
            category="Dispatched",
            subcategory=_nonnull(rec.get("priority") or rec.get("close_type") or ""),
            description=_nonnull(desc),
            occurred_at=(
                rec.get("start_time")
                or rec.get("start_date_time")
                or rec.get("dispatch_date_time")
            ),
            reported_at=rec.get("end_time") or rec.get("end_date_time"),
            lat=lat,
            lon=lon,
            address=_nonnull(rec.get("address") or rec.get("location_address") or ""),
            zip_code=_nonnull(rec.get("zip")) or settings.zip,
            raw_url=_row_url(base, incident_id),
            raw=rec,
        ))
    return out


def _is_ems(call_type: str) -> bool:
    c = call_type.lower()
    return any(k in c for k in ["ems", "medical", "ambulance", "sick", "injury", "overdose", "bleed", "chest", "breath", "cardiac", "fall"])


def fire_ems_to_outputs(r: FetchResult, settings: Settings) -> tuple[list[Incident], list[StationSummary]]:
    incidents: list[Incident] = []
    daily: dict[tuple[str, str], dict[str, int]] = {}

    meta = r.meta or {}
    for rec in meta.get("station_rows", []):
        station_id = str(rec.get("fire_station_number") or rec.get("fire_station") or "?")
        date_val = str(rec.get("date") or "")[:10]
        call_type = str(rec.get("call_type_description") or "Fire/EMS call")
        time_val = str(rec.get("time") or "")
        occurred_at = f"{date_val}T{time_val}" if date_val and time_val else (date_val or None)

        lat, lon = parse_latlon(rec, "location")
        incident_id = str(rec.get("incident_number") or rec.get(":id") or f"fe-{len(incidents)}")
        is_ems = _is_ems(call_type)
        incidents.append(Incident(
            id=f"fire_ems-{incident_id}",
            source="fire_ems",
            category="EMS" if is_ems else "Fire",
            subcategory=call_type,
            description=call_type,
            occurred_at=occurred_at,
            reported_at=None,
            lat=lat,
            lon=lon,
            address=_nonnull(rec.get("station_address") or ""),
            zip_code=settings.zip,
            raw_url="",
            raw=rec,
        ))

        key = (station_id, date_val)
        bucket = daily.setdefault(key, {"ems": 0, "fire": 0})
        bucket["ems" if is_ems else "fire"] += 1

    summaries: list[StationSummary] = [
        StationSummary(station=st, date=dt, ems_count=b["ems"], fire_count=b["fire"])
        for (st, dt), b in sorted(daily.items())
    ]

    for rec in meta.get("overdose_rows", []):
        lat, lon = parse_latlon(rec, "latitude", "longitude")
        if lat is None:
            lat, lon = parse_latlon(rec, "location")
        incident_id = str(rec.get("incident_id") or rec.get(":id") or f"od-{len(incidents)}")
        incidents.append(Incident(
            id=f"overdose-{incident_id}",
            source="fire_ems",
            category="Overdose",
            subcategory=_nonnull(rec.get("incident_type") or "Overdose"),
            description=_nonnull(rec.get("incident_type") or "Overdose response"),
            occurred_at=rec.get("incident_date_time"),
            reported_at=None,
            lat=lat,
            lon=lon,
            address=_nonnull(rec.get("address") or ""),
            zip_code=_nonnull(rec.get("zip_code")) or settings.zip,
            raw_url="",
            raw=rec,
        ))

    return incidents, summaries
