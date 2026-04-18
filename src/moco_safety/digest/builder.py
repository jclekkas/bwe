from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..config import Settings

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def _within_hours(iso: str | None, hours: int, now: datetime) -> bool:
    d = _parse_iso(iso)
    if d is None:
        return False
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now - d) <= timedelta(hours=hours)


def _group_by(items: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for it in items:
        k = it.get(key) or "Other"
        out.setdefault(k, []).append(it)
    return out


def build_sections(
    snapshot: dict,
    settings: Settings,
    previous: dict | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    hours = settings.digest_hours

    incidents = snapshot.get("incidents", [])
    crime = [i for i in incidents if i["source"] == "crime" and _within_hours(i.get("occurred_at"), hours, now)]
    dispatched = [i for i in incidents if i["source"] == "dispatched" and _within_hours(i.get("occurred_at"), hours, now)]
    overdoses = [i for i in incidents if i["source"] == "fire_ems" and _within_hours(i.get("occurred_at"), 7 * 24, now)]

    sources = snapshot.get("sources", {})

    return {
        "date": now.strftime("%Y-%m-%d"),
        "zip": snapshot.get("zip"),
        "generated_at": snapshot.get("generated_at"),
        "ui_url": settings.digest.get("ui_url") or "",
        "sources": sources,
        "crime": {
            "status": sources.get("crime", {}).get("status", "error"),
            "note": sources.get("crime", {}).get("note", ""),
            "rows": crime,
            "by_category": _group_by(crime, "category"),
        },
        "dispatched": {
            "status": sources.get("dispatched", {}).get("status", "error"),
            "note": sources.get("dispatched", {}).get("note", ""),
            "rows": dispatched,
        },
        "fire_ems": {
            "status": sources.get("fire_ems", {}).get("status", "error"),
            "note": sources.get("fire_ems", {}).get("note", ""),
            "station_summary": snapshot.get("fire_ems_station_summary", []),
            "overdoses": overdoses,
        },
    }


def render(snapshot: dict, settings: Settings, previous: dict | None) -> tuple[str, str, str]:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ctx = build_sections(snapshot, settings, previous)
    html = env.get_template("digest.html.j2").render(**ctx)
    text = env.get_template("digest.txt.j2").render(**ctx)
    subject = f"{settings.digest.get('subject_prefix', 'Digest')} — {ctx['date']}"
    return subject, html, text
