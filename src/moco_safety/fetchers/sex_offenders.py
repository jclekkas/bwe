from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..config import CACHE_DIR, Settings
from ..models import FetchResult
from ..util.cache import HtmlCache, JsonCache
from ..util.http import RateLimiter, get

BASE = "https://www.icrimewatch.net/"


class SexOffenderFetcher:
    """Scrapes the Maryland iCrimeWatch registry results for a given ZIP.

    HTML structure is volatile — this fetcher deliberately errors loudly
    (status=error) rather than returning a silently-empty list.
    """

    name = "offenders"

    def fetch(self, settings: Settings, since: datetime) -> FetchResult:
        cfg = settings.source("offenders")
        if not cfg.get("enabled"):
            return FetchResult(self.name, "ok", "disabled")

        limiter = RateLimiter(float(cfg.get("rate_limit_seconds", 2.0)))
        ttl = float(cfg.get("cache_ttl_days", 7)) * 86400
        html_cache = HtmlCache(CACHE_DIR / "offenders", ttl)
        geocode = JsonCache(CACHE_DIR / "geocode.json")

        try:
            results_html = self._fetch_results(cfg["agency_id"], settings.zip, limiter)
            profiles = self._parse_results(results_html)
            if not profiles:
                return FetchResult(
                    self.name, "ok",
                    "no offenders listed for ZIP (or parse returned zero — inspect manually)",
                    records=[],
                )

            offenders: list[dict] = []
            for p in profiles:
                key = p["profile_url"]
                html = html_cache.get(key)
                if html is None:
                    r = get(p["profile_url"], limiter=limiter)
                    html = r.text
                    html_cache.put(key, html)
                details = self._parse_profile(html)
                if details.get("lat") is None and details.get("address"):
                    details["lat"], details["lon"] = self._geocode(details["address"], geocode, limiter)
                offenders.append({**p, **details})

            return FetchResult(
                self.name, "ok",
                f"{len(offenders)} offenders",
                records=offenders,
                meta={"agency_id": cfg["agency_id"], "zip": settings.zip},
            )
        except Exception as e:
            return FetchResult(self.name, "error", f"{type(e).__name__}: {e}")

    # --- helpers ---

    def _fetch_results(self, agency_id: str, zip_code: str, limiter: RateLimiter) -> str:
        url = urljoin(BASE, "results.php")
        r = get(
            url,
            params={"AgencyID": agency_id, "SubmitZip": "Zip Code", "Zip": zip_code},
            limiter=limiter,
        )
        r.raise_for_status()
        return r.text

    def _parse_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        # icrimewatch result rows typically link to detail.php?OfndrID=...
        for a in soup.select("a[href*='detail.php']"):
            href = a.get("href", "")
            if "OfndrID" not in href:
                continue
            profile_url = urljoin(BASE, href)
            m = re.search(r"OfndrID=(\d+)", href)
            ofndr_id = m.group(1) if m else profile_url
            name = a.get_text(strip=True) or f"Offender {ofndr_id}"
            if not any(x["id"] == ofndr_id for x in out):
                out.append({
                    "id": ofndr_id,
                    "name": name,
                    "profile_url": profile_url,
                })
        return out

    def _parse_profile(self, html: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        out: dict = {
            "address": "",
            "zip_code": "",
            "offenses": [],
            "last_verified": None,
            "photo_url": None,
            "lat": None,
            "lon": None,
        }

        img = soup.find("img", src=re.compile(r"photos?|offender", re.I))
        if img and img.get("src"):
            out["photo_url"] = urljoin(BASE, img["src"])

        addr_match = re.search(
            r"([0-9][^\n]+?,\s*[A-Z][A-Za-z .]+,\s*MD\s*\d{5})", text
        )
        if addr_match:
            out["address"] = addr_match.group(1).strip()
            zm = re.search(r"(\d{5})\s*$", out["address"])
            if zm:
                out["zip_code"] = zm.group(1)

        # Offenses often appear under a heading; keep it conservative.
        for li in soup.select("li"):
            t = li.get_text(" ", strip=True)
            if re.search(r"\b(offense|charge|conviction|statute)\b", t, re.I):
                out["offenses"].append(t)

        lv = re.search(r"(?:Last Verified|Verified)[:\s]+([0-9/.\-]+)", text, re.I)
        if lv:
            out["last_verified"] = lv.group(1)

        return out

    def _geocode(self, address: str, cache: JsonCache, limiter: RateLimiter):
        cached = cache.get(address)
        if cached:
            return cached.get("lat"), cached.get("lon")
        try:
            r = get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": 1, "countrycodes": "us"},
                headers={"Accept": "application/json"},
                limiter=limiter,
            )
            data = r.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                cache.put(address, {"lat": lat, "lon": lon})
                return lat, lon
        except Exception:
            pass
        cache.put(address, {"lat": None, "lon": None})
        return None, None
