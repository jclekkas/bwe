"""Smoke tests that exercise the sex-offender HTML parser with a canned fixture."""
from pathlib import Path

from moco_safety.fetchers.sex_offenders import SexOffenderFetcher


FIXTURE_DIR = Path(__file__).parent / "fixtures"


BASE = "http://example.com/"


def test_parse_results_extracts_profile_links():
    html = (FIXTURE_DIR / "offender_results.html").read_text()
    f = SexOffenderFetcher()
    out = f._parse_results(html, BASE)
    assert len(out) == 2
    assert out[0]["id"] == "111"
    assert out[0]["name"] == "DOE, JOHN"
    assert "detail.php?OfndrID=111" in out[0]["profile_url"]


def test_parse_profile_extracts_address_and_offenses():
    html = (FIXTURE_DIR / "offender_profile.html").read_text()
    f = SexOffenderFetcher()
    out = f._parse_profile(html, BASE)
    assert "GERMANTOWN" in out["address"].upper()
    assert out["zip_code"] == "20874"
    assert out["last_verified"] == "2025-03-15"
    assert any("offense" in o.lower() for o in out["offenses"])
