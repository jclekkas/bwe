from datetime import datetime, timezone

from moco_safety.config import load_settings
from moco_safety.digest import builder


def _snap(**over):
    base = {
        "generated_at": "2026-04-18T11:00:00+00:00",
        "zip": "20874",
        "window_days": 7,
        "sources": {
            "crime": {"status": "ok", "note": "4 rows"},
            "dispatched": {"status": "ok", "note": ""},
            "fire_ems": {"status": "degraded", "note": "aggregate only"},
        },
        "incidents": [
            {
                "id": "crime-1", "source": "crime", "category": "Property",
                "subcategory": "Larceny", "description": "Theft from Vehicle",
                "occurred_at": "2026-04-18T01:00:00+00:00",
                "lat": 39.17, "lon": -77.24, "address": "100 MAIN ST", "zip_code": "20874", "raw_url": "",
            },
            {
                "id": "dispatched-1", "source": "dispatched", "category": "Dispatched",
                "subcategory": "", "description": "Noise complaint",
                "occurred_at": "2026-04-18T02:00:00+00:00",
                "lat": 39.18, "lon": -77.24, "address": "GREAT SENECA HWY", "zip_code": "20874", "raw_url": "",
            },
        ],
        "fire_ems_station_summary": [
            {"station": "29", "date": "2026-04-17", "ems_count": 5, "fire_count": 1},
        ],
    }
    base.update(over)
    return base


def test_build_sections_24h_window():
    settings = load_settings()
    snap = _snap()
    now = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)
    ctx = builder.build_sections(snap, settings, previous=None, now=now)
    assert ctx["crime"]["rows"][0]["description"] == "Theft from Vehicle"
    assert ctx["dispatched"]["rows"][0]["description"] == "Noise complaint"


def test_render_produces_html_and_text():
    settings = load_settings()
    snap = _snap()
    subject, html, text = builder.render(snap, settings, previous=None)
    assert "20874" in subject
    assert "Daily Safety Digest" in html
    assert "Daily Safety Digest" in text
