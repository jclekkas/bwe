from moco_safety.config import load_categories, load_settings
from moco_safety.models import FetchResult
from moco_safety.normalize import (
    crime_to_incidents,
    dispatched_to_incidents,
    fire_ems_to_outputs,
    offenders_to_records,
)


def test_crime_to_incidents():
    settings = load_settings()
    cats = load_categories()
    r = FetchResult(
        source="crime",
        status="ok",
        records=[{
            "incident_id": "42",
            "crimename1": "Crime Against Property",
            "crimename2": "Larceny",
            "crimename3": "Theft from Vehicle",
            "start_date": "2026-04-17T10:00:00.000",
            "address": "100 MAIN ST",
            "zip_code": "20874",
            "latitude": "39.17",
            "longitude": "-77.24",
        }],
    )
    out = crime_to_incidents(r, settings, cats)
    assert len(out) == 1
    i = out[0]
    assert i.source == "crime"
    assert i.category == "Property"
    assert i.subcategory == "Larceny"
    assert i.description == "Theft from Vehicle"
    assert i.zip_code == "20874"
    assert i.lat == 39.17
    assert i.lon == -77.24


def test_dispatched_to_incidents():
    settings = load_settings()
    r = FetchResult(
        source="dispatched",
        status="ok",
        records=[{
            ":id": "abc",
            "incident_type": "Disturbance",
            "start_date_time": "2026-04-17T22:00:00.000",
            "location_address": "GREAT SENECA HWY",
            "latitude": "39.18",
            "longitude": "-77.25",
        }],
    )
    out = dispatched_to_incidents(r, settings)
    assert out[0].description == "Disturbance"
    assert out[0].lat == 39.18


def test_fire_ems_mixed():
    settings = load_settings()
    r = FetchResult(
        source="fire_ems",
        status="ok",
        meta={
            "station_rows": [
                {"fire_station_number": "29", "fire_station": "Station 29",
                 "date": "2026-04-17", "time": "12:00:00",
                 "call_type_description": "EMS - Sick Person",
                 "incident_number": "F1", "station_address": "1 MAIN"},
                {"fire_station_number": "29", "fire_station": "Station 29",
                 "date": "2026-04-17", "time": "13:00:00",
                 "call_type_description": "EMS - Fall Injury",
                 "incident_number": "F2", "station_address": "2 MAIN"},
                {"fire_station_number": "29", "fire_station": "Station 29",
                 "date": "2026-04-17", "time": "14:00:00",
                 "call_type_description": "Structure Fire",
                 "incident_number": "F3", "station_address": "3 MAIN"},
            ],
            "overdose_rows": [{
                "incident_id": "od-1",
                "incident_date_time": "2026-04-16T03:00:00.000",
                "incident_type": "Opioid overdose",
                "latitude": "39.17",
                "longitude": "-77.24",
                "address": "ANYWHERE",
            }],
        },
    )
    incidents, summaries = fire_ems_to_outputs(r, settings)
    assert len(summaries) == 1
    assert summaries[0].station == "29"
    assert summaries[0].ems_count == 2
    assert summaries[0].fire_count == 1
    # 3 fire/ems incidents + 1 overdose
    assert len(incidents) == 4
    assert any(i.category == "Overdose" for i in incidents)
    assert any(i.category == "EMS" for i in incidents)
    assert any(i.category == "Fire" for i in incidents)


def test_offenders():
    r = FetchResult(
        source="offenders",
        status="ok",
        records=[{
            "id": "999",
            "name": "TEST PERSON",
            "profile_url": "https://example.com/detail.php?OfndrID=999",
            "address": "500 FAKE ST, GERMANTOWN, MD 20874",
            "zip_code": "20874",
            "offenses": ["Test offense"],
            "last_verified": "2026-01-01",
            "photo_url": None,
            "lat": 39.17,
            "lon": -77.24,
        }],
    )
    out = offenders_to_records(r)
    assert out[0].name == "TEST PERSON"
    assert out[0].zip_code == "20874"
