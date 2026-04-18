from __future__ import annotations

from typing import Optional

from .config import Settings
from .models import FetchResult, Incident, Offender, StationSummary
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
            lat, lon = parse_latlon(rec, "location")
        desc = rec.get("incident_type") or rec.get("description") or "Dispatched call"
        incident_id = str(
            rec.get("incident_id") or rec.get(":id") or rec.get("event_id") or f"d-{len(out)}"
        )
        out.append(Incident(
            id=f"dispatched-{incident_id}",
            source="dispatched",
            category="Dispatched",
            subcategory=_nonnull(rec.get("incident_type_category") or rec.get("priority") or ""),
            description=_nonnull(desc),
            occurred_at=rec.get("start_date_time") or rec.get("dispatch_date_time"),
            reported_at=rec.get("end_date_time"),
            lat=lat,
            lon=lon,
            address=_nonnull(rec.get("location_address") or rec.get("address") or ""),
            zip_code=settings.zip,
            raw_url=_row_url(base, incident_id),
            raw=rec,
        ))
    return out


def fire_ems_to_outputs(r: FetchResult, settings: Settings) -> tuple[list[Incident], list[StationSummary]]:
    incidents: list[Incident] = []
    summaries: list[StationSummary] = []

    meta = r.meta or {}
    for s in meta.get("station_rows", []):
        summaries.append(StationSummary(
            station=str(s.get("station_number") or s.get("station") or "?"),
            date=str(s.get("date") or s.get("incident_date") or ""),
            ems_count=int(float(s.get("ems_count") or s.get("ems") or 0) or 0),
            fire_count=int(float(s.get("fire_count") or s.get("fire") or 0) or 0),
        ))

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


def offenders_to_records(r: FetchResult) -> list[Offender]:
    out: list[Offender] = []
    for rec in r.records:
        out.append(Offender(
            id=str(rec.get("id")),
            name=rec.get("name", ""),
            address=rec.get("address", ""),
            zip_code=rec.get("zip_code", ""),
            offenses=rec.get("offenses", []),
            last_verified=rec.get("last_verified"),
            photo_url=rec.get("photo_url"),
            profile_url=rec.get("profile_url", ""),
            lat=rec.get("lat"),
            lon=rec.get("lon"),
        ))
    return out
