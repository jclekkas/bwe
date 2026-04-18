"""Generate a richer demo snapshot at data/snapshot.json.

This fills the explorer with ~1 year of plausible ZIP 20874 data until the
real cron runs and overwrites the file with live MoCo records.

Deterministic: uses a fixed random seed so reruns produce the same output
and git diffs stay sane.

Usage:
    python scripts/gen_demo_snapshot.py
"""
from __future__ import annotations

import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "snapshot.json"

GENERATED_AT = datetime(2026, 4, 18, 11, 15, tzinfo=timezone.utc)
ZIP = "20874"

# Realistic Germantown streets with approximate coordinates inside the ZIP.
STREETS = [
    ("19400 BLOCK GERMANTOWN RD", 39.178, -77.252),
    ("13200 BLOCK CLOPPER RD", 39.166, -77.262),
    ("MILESTONE SHOPPING CENTER", 39.189, -77.240),
    ("GREAT SENECA HWY", 39.172, -77.278),
    ("19300 BLOCK OBSERVATION DR", 39.195, -77.225),
    ("13500 BLOCK WISTERIA DR", 39.158, -77.267),
    ("18900 BLOCK CRYSTAL ROCK DR", 39.181, -77.256),
    ("MIDDLEBROOK RD & GREAT SENECA HWY", 39.171, -77.244),
    ("NORTH LAKE PARK", 39.164, -77.230),
    ("12900 BLOCK WISTERIA DR", 39.177, -77.283),
    ("13100 BLOCK MIDDLEBROOK RD", 39.169, -77.259),
    ("18600 BLOCK MIDDLEBROOK RD", 39.175, -77.260),
    ("20000 BLOCK FATHER HURLEY BLVD", 39.188, -77.246),
    ("19700 BLOCK EXECUTIVE PARK CIR", 39.199, -77.230),
    ("13800 BLOCK CENTURY BLVD", 39.155, -77.270),
    ("19100 BLOCK WATERSIDE DR", 39.192, -77.258),
    ("12500 BLOCK MILESTONE PKWY", 39.163, -77.238),
    ("18400 BLOCK SOUTH VALLEY DR", 39.170, -77.274),
]

CRIME_OFFENSES = [
    ("Property", "Larceny", "Theft from Vehicle", "23H"),
    ("Property", "Larceny", "Theft from Building", "23E"),
    ("Property", "Larceny", "Shoplifting", "23C"),
    ("Property", "Larceny", "Pocket-picking", "23A"),
    ("Property", "Burglary", "Residential Burglary - Forced Entry", "220"),
    ("Property", "Burglary", "Burglary Commercial", "221"),
    ("Property", "Motor Vehicle Theft", "Stolen Auto", "240"),
    ("Property", "Motor Vehicle Theft", "Attempted MV Theft", "241"),
    ("Property", "Vandalism", "Vandalism to Property", "290"),
    ("Property", "Vandalism", "Graffiti", "291"),
    ("Violent", "Assault", "Simple Assault", "13B"),
    ("Violent", "Assault", "Aggravated Assault", "13A"),
    ("Violent", "Robbery", "Strong-arm Robbery", "120"),
    ("Violent", "Robbery", "Armed Robbery", "121"),
    ("Drug", "Drug/Narcotic", "Drug Possession", "35A"),
    ("Drug", "Drug/Narcotic", "Drug Paraphernalia", "35B"),
    ("Other", "Fraud", "Credit Card Fraud", "26B"),
    ("Other", "Fraud", "Identity Theft", "26F"),
    ("Other", "DUI", "Driving Under the Influence", "90D"),
    ("Other", "Weapon Law Violations", "Weapon Violation", "520"),
]

DISPATCH_TYPES = [
    ("Priority 2", "Noise Complaint"),
    ("Priority 1", "Traffic Collision with Injury"),
    ("Priority 3", "Suspicious Person"),
    ("Priority 2", "Disturbance"),
    ("Priority 2", "Shoplifting Report"),
    ("Priority 1", "Person with Weapon"),
    ("Priority 3", "Parking Complaint"),
    ("Priority 2", "Welfare Check"),
    ("Priority 3", "Lost / Found Property"),
    ("Priority 2", "Civil Dispute"),
    ("Priority 1", "Assault in Progress"),
    ("Priority 2", "Alarm - Commercial"),
    ("Priority 3", "Animal Complaint"),
    ("Priority 2", "Road Hazard"),
]

POLICE_DISTRICTS = ["5D (Germantown)", "5D (Germantown)", "5D (Germantown)", "6D (Montgomery Village)"]
BEATS = ["5D21", "5D22", "5D23", "5D24"]


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def jitter_latlon(lat: float, lon: float, rng: random.Random) -> tuple[float, float]:
    # ±0.003° jitter so markers don't overlap exactly (~300m at this latitude).
    return round(lat + rng.uniform(-0.003, 0.003), 5), round(lon + rng.uniform(-0.003, 0.003), 5)


def make_crime(i: int, when: datetime, rng: random.Random) -> dict:
    category, subcategory, description, nibrs = rng.choice(CRIME_OFFENSES)
    street, lat, lon = rng.choice(STREETS)
    lat, lon = jitter_latlon(lat, lon, rng)
    end = when + timedelta(minutes=rng.randint(15, 240))
    case = f"260{rng.randint(0, 999999):06d}"
    dispatch_district = rng.choice(POLICE_DISTRICTS)
    beat = rng.choice(BEATS)
    raw = {
        "incident_id": f"2026{i:08d}",
        "cr_number": case,
        "offense_code": nibrs,
        "crimename1": category,
        "crimename2": subcategory,
        "crimename3": description,
        "start_date": iso(when),
        "end_date": iso(end),
        "address": street,
        "city": "GERMANTOWN",
        "state": "MD",
        "zip_code": ZIP,
        "latitude": str(lat),
        "longitude": str(lon),
        "agency": "MCPD",
        "place": rng.choice(["Residence/Home", "Parking Lot", "Commercial/Office", "Street", "Restaurant"]),
        "police_district_name": dispatch_district,
        "police_district_number": dispatch_district[:2],
        "beat": beat,
        "pra": str(rng.randint(1000, 9999)),
        "street_prefix": "",
        "street_name": street.split(" BLOCK ")[-1] if " BLOCK " in street else street,
        "sector": dispatch_district[:2],
        "victims": str(rng.randint(0, 2)),
    }
    return {
        "id": f"crime-{raw['incident_id']}",
        "source": "crime",
        "category": category,
        "subcategory": subcategory,
        "description": description,
        "occurred_at": iso(when),
        "reported_at": iso(end),
        "lat": lat,
        "lon": lon,
        "address": street,
        "zip_code": ZIP,
        "raw_url": f"https://data.montgomerycountymd.gov/Public-Safety/Crime/icn6-v9z3/row/{raw['incident_id']}",
        "raw": raw,
    }


def make_dispatched(i: int, when: datetime, rng: random.Random) -> dict:
    priority, description = rng.choice(DISPATCH_TYPES)
    street, lat, lon = rng.choice(STREETS)
    lat, lon = jitter_latlon(lat, lon, rng)
    cleared = when + timedelta(minutes=rng.randint(5, 120))
    raw = {
        "incident_id": f"D2026{i:06d}",
        "incident_type": description,
        "priority": priority,
        "start_date_time": iso(when),
        "end_date_time": iso(cleared),
        "dispatch_date_time": iso(when + timedelta(minutes=rng.randint(0, 5))),
        "arrived_date_time": iso(when + timedelta(minutes=rng.randint(5, 20))),
        "location_address": street,
        "city": "GERMANTOWN",
        "zip_code": ZIP,
        "latitude": str(lat),
        "longitude": str(lon),
        "police_district": rng.choice(POLICE_DISTRICTS),
        "beat": rng.choice(BEATS),
        "call_source": rng.choice(["911", "Non-emergency line", "Officer initiated"]),
        "units_dispatched": str(rng.randint(1, 4)),
    }
    return {
        "id": f"dispatched-{raw['incident_id']}",
        "source": "dispatched",
        "category": "Dispatched",
        "subcategory": priority,
        "description": description,
        "occurred_at": iso(when),
        "reported_at": iso(cleared),
        "lat": lat,
        "lon": lon,
        "address": street,
        "zip_code": ZIP,
        "raw_url": f"https://data.montgomerycountymd.gov/Public-Safety/Police-Dispatched-Incidents/98cc-bc7d/row/{raw['incident_id']}",
        "raw": raw,
    }


def make_overdose(i: int, when: datetime, rng: random.Random) -> dict:
    street, lat, lon = rng.choice(STREETS)
    lat, lon = jitter_latlon(lat, lon, rng)
    drugs = rng.choice(["Opioid", "Heroin", "Fentanyl", "Mixed substance"])
    raw = {
        "incident_id": f"FR2026{i:06d}",
        "incident_type": f"{drugs} Overdose",
        "incident_date_time": iso(when),
        "address": street,
        "zip_code": ZIP,
        "latitude": str(lat),
        "longitude": str(lon),
        "narcan_administered": rng.choice(["Yes", "No"]),
        "transport_to": rng.choice(["Shady Grove Adventist", "Holy Cross Germantown", "Refused Transport"]),
        "age_range": rng.choice(["18-25", "26-35", "36-45", "46-55", "56+"]),
        "gender": rng.choice(["M", "F"]),
    }
    return {
        "id": f"overdose-{raw['incident_id']}",
        "source": "fire_ems",
        "category": "Overdose",
        "subcategory": drugs,
        "description": f"{drugs} Overdose Response",
        "occurred_at": iso(when),
        "reported_at": None,
        "lat": lat,
        "lon": lon,
        "address": street,
        "zip_code": ZIP,
        "raw_url": f"https://data.montgomerycountymd.gov/Public-Safety/Fire-Incidents-Overdoses/4wcf-kdya/row/{raw['incident_id']}",
        "raw": raw,
    }


def make_station_summary(station: str, date: datetime, rng: random.Random) -> dict:
    return {
        "station": station,
        "date": date.strftime("%Y-%m-%d"),
        "ems_count": rng.randint(5, 25),
        "fire_count": rng.randint(0, 4),
    }


def main() -> None:
    rng = random.Random(20874)  # deterministic

    incidents: list[dict] = []
    # 180 crime incidents spread over the last year, with a slight recent bias.
    for i in range(180):
        age_hours = int(rng.triangular(1, 24 * 365, 24 * 30))
        when = GENERATED_AT - timedelta(hours=age_hours)
        incidents.append(make_crime(i, when, rng))

    # 220 dispatched calls — higher volume, same time range.
    for i in range(220):
        age_hours = int(rng.triangular(1, 24 * 365, 24 * 20))
        when = GENERATED_AT - timedelta(hours=age_hours)
        incidents.append(make_dispatched(i, when, rng))

    # 14 overdoses in the last 6 months.
    for i in range(14):
        age_hours = int(rng.uniform(24, 24 * 180))
        when = GENERATED_AT - timedelta(hours=age_hours)
        incidents.append(make_overdose(i, when, rng))

    # Station summaries: last 14 days × 2 stations.
    station_summary = []
    for d in range(14):
        date = GENERATED_AT - timedelta(days=d)
        station_summary.append(make_station_summary("29", date, rng))
        station_summary.append(make_station_summary("33", date, rng))

    offenders = [
        {"id": "demo-1", "name": "DEMO, SAMPLE A", "address": "19000 BLOCK GERMANTOWN RD, GERMANTOWN, MD 20874",
         "zip_code": ZIP, "offenses": ["Demo registry entry — real registry populated by cron"],
         "last_verified": "2026-02-10", "photo_url": None, "profile_url": "#demo",
         "lat": 39.184, "lon": -77.249},
        {"id": "demo-2", "name": "DEMO, SAMPLE B", "address": "13300 BLOCK CLOPPER RD, GERMANTOWN, MD 20874",
         "zip_code": ZIP, "offenses": ["Demo registry entry — real registry populated by cron"],
         "last_verified": "2025-11-04", "photo_url": None, "profile_url": "#demo",
         "lat": 39.163, "lon": -77.268},
        {"id": "demo-3", "name": "DEMO, SAMPLE C", "address": "18600 BLOCK MIDDLEBROOK RD, GERMANTOWN, MD 20874",
         "zip_code": ZIP, "offenses": ["Demo registry entry — real registry populated by cron"],
         "last_verified": "2026-01-22", "photo_url": None, "profile_url": "#demo",
         "lat": 39.175, "lon": -77.260},
    ]

    snap = {
        "generated_at": iso(GENERATED_AT),
        "zip": ZIP,
        "window_days": 365,
        "sources": {
            "crime": {"status": "ok", "note": f"demo: {sum(1 for i in incidents if i['source']=='crime')} rows across 365 days", "count": sum(1 for i in incidents if i['source'] == 'crime')},
            "dispatched": {"status": "ok", "note": f"demo: {sum(1 for i in incidents if i['source']=='dispatched')} rows across 365 days", "count": sum(1 for i in incidents if i['source'] == 'dispatched')},
            "fire_ems": {"status": "degraded", "note": "demo: station aggregates + overdoses", "count": sum(1 for i in incidents if i['source'] == 'fire_ems'), "granularity": "mixed"},
            "offenders": {"status": "ok", "note": "demo: 3 placeholder records", "count": len(offenders)},
        },
        "incidents": sorted(incidents, key=lambda x: x["occurred_at"], reverse=True),
        "fire_ems_station_summary": station_summary,
        "offenders": offenders,
        "offenders_stale_copy": [],
    }

    OUT.write_text(json.dumps(snap, indent=2))
    print(f"wrote {OUT} — {len(incidents)} incidents, {len(offenders)} offenders")


if __name__ == "__main__":
    main()
