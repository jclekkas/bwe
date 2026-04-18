from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from ..config import CACHE_DIR, Settings
from ..models import FetchResult
from ..util.cache import HtmlCache, JsonCache
from ..util.http import RateLimiter, get

# Maryland Sex Offender Registry (DPSCS WebSOR). Public, updated daily.
BASE = "https://www.dpscs.state.md.us/sorSearch/"
SEARCH_URL = BASE + "search.do"


class SexOffenderFetcher:
    """Scrapes the Maryland state DPSCS sex-offender registry for a given ZIP.

    Tries several parameter shapes since the form spec isn't documented; logs
    response status + size to the FetchResult note so the snapshot.meta.json
    surfaces what worked.
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

        notes: list[str] = []
        results_html = None
        try:
            param_attempts = [
                {"searchType": "byZip", "zip": settings.zip},
                {"searchType": "byZip", "zipCode": settings.zip},
                {"searchType": "byZip", "Zip": settings.zip},
                {"searchType": "byZip", "zip_code": settings.zip},
            ]
            for params in param_attempts:
                try:
                    r = get(SEARCH_URL, params=params, limiter=limiter, timeout=30)
                    notes.append(f"GET {params}: {r.status_code} ({len(r.text)} bytes)")
                    if r.status_code == 200 and len(r.text) > 1000:
                        results_html = r.text
                        used_params = params
                        break
                except Exception as e:
                    notes.append(f"GET {params}: {type(e).__name__}: {str(e)[:80]}")
                    continue

            if results_html is None:
                return FetchResult(self.name, "error", "; ".join(notes))

            profiles = self._parse_results(results_html)
            notes.append(f"parsed {len(profiles)} profile links")
            if not profiles:
                # Could be a legitimate empty result OR a parse-format change.
                # Save first 600 chars of body for debugging.
                snippet = re.sub(r"\s+", " ", results_html[:600])
                notes.append(f"body snippet: {snippet}")
                return FetchResult(self.name, "ok", "; ".join(notes), records=[],
                                   meta={"used_params": used_params})

            offenders: list[dict] = []
            for p in profiles:
                profile_url = p["profile_url"]
                html = html_cache.get(profile_url)
                if html is None:
                    try:
                        rp = get(profile_url, limiter=limiter)
                        html = rp.text
                        html_cache.put(profile_url, html)
                    except Exception as e:
                        notes.append(f"profile {p['id']}: {type(e).__name__}")
                        continue
                details = self._parse_profile(html)
                if details.get("lat") is None and details.get("address"):
                    details["lat"], details["lon"] = self._geocode(
                        details["address"], geocode, limiter
                    )
                offenders.append({**p, **details})

            return FetchResult(
                self.name, "ok",
                f"{len(offenders)} offenders | {'; '.join(notes)}",
                records=offenders,
                meta={"used_params": used_params, "zip": settings.zip},
            )
        except Exception as e:
            notes.append(f"{type(e).__name__}: {str(e)[:200]}")
            return FetchResult(self.name, "error", "; ".join(notes))

    def _parse_results(self, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        # Try to find detail links — DPSCS uses search.do?searchType=detail or
        # offenderProfile.do or similar. Be permissive about the link target.
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            if not any(token in href.lower() for token in ["detail", "profile", "offender", "sornum", "id="]):
                continue
            url = urljoin(BASE, href)
            # Skip same-page anchors
            if not urlparse(url).netloc:
                continue
            # Extract an id from the URL query string if possible
            m = re.search(r"(?:sorNum|offenderId|id|num)=([A-Za-z0-9_-]+)", href, re.I)
            ofndr_id = m.group(1) if m else url
            name = a.get_text(" ", strip=True)
            if not name or len(name) < 3:
                continue
            if any(x["id"] == ofndr_id for x in out):
                continue
            out.append({"id": str(ofndr_id), "name": name, "profile_url": url})
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
        img = soup.find("img", src=re.compile(r"photo|offender|sor", re.I))
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

        for li in soup.select("li, td, p"):
            t = li.get_text(" ", strip=True)
            if re.search(r"\b(offense|charge|conviction|statute|crime)\b", t, re.I) and len(t) < 300:
                out["offenses"].append(t)

        lv = re.search(r"(?:Last Verified|Verified|Last Verification)[:\s]+([0-9/.\-]+)", text, re.I)
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
