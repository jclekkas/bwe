from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from ..config import CACHE_DIR, Settings
from ..models import FetchResult
from ..util.cache import HtmlCache, JsonCache
from ..util.http import RateLimiter, USER_AGENT

# Maryland Sex Offender Registry (DPSCS WebSOR). Public, updated daily.
# The site is a Java Struts app that requires an agreement-checkbox cookie
# (CHECKBOX_1=on) to be set before search.do will return real results, and it
# tracks the session via JSESSIONID. HTTPS on the dpscs.state.md.us host has
# a flaky cert chain from some egress networks, so we try HTTP first, fall
# back to HTTPS with cert verification disabled.
HTTP_BASE = "http://www.dpscs.state.md.us/sorSearch/"
HTTPS_BASE = "https://www.dpscs.state.md.us/sorSearch/"


class SexOffenderFetcher:
    """Scrapes the Maryland state DPSCS sex-offender registry for a given ZIP."""

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
        used_base = None
        used_params: dict = {}

        for base in (HTTP_BASE, HTTPS_BASE):
            verify = base.startswith("https")  # will flip to False on retry
            for attempt_verify in ([True, False] if not verify else [False]):
                try:
                    session = self._new_session(base)
                    # 1) land on agreement page — sets JSESSIONID
                    r1 = self._req(session, base, limiter=limiter, verify=attempt_verify)
                    notes.append(f"{base} landing: {r1.status_code} ({len(r1.text)} bytes)")
                    # 2) accept the agreement checkbox
                    r2 = self._req(session, base, params={"CHECKBOX_1": "on"},
                                   limiter=limiter, verify=attempt_verify)
                    notes.append(f"{base} agree: {r2.status_code} ({len(r2.text)} bytes)")
                    # 3) search by ZIP — try documented shape
                    params = {"searchType": "byZip", "zip": settings.zip}
                    r3 = self._req(session, base + "search.do", params=params,
                                   limiter=limiter, verify=attempt_verify,
                                   referer=base)
                    notes.append(f"{base} search {params}: {r3.status_code} ({len(r3.text)} bytes)")
                    if r3.status_code == 200 and len(r3.text) > 800:
                        results_html = r3.text
                        used_base = base
                        used_params = params
                        used_session = session
                        used_verify = attempt_verify
                        break
                except Exception as e:
                    notes.append(f"{base} (verify={attempt_verify}): {type(e).__name__}: {str(e)[:120]}")
                    continue
            if results_html is not None:
                break

        if results_html is None:
            return FetchResult(self.name, "error", "; ".join(notes))

        profiles = self._parse_results(results_html, used_base)
        notes.append(f"parsed {len(profiles)} profile links")
        if not profiles:
            snippet = re.sub(r"\s+", " ", results_html[:800])
            notes.append(f"body snippet: {snippet}")
            return FetchResult(self.name, "ok", "; ".join(notes), records=[],
                               meta={"used_params": used_params, "used_base": used_base})

        offenders: list[dict] = []
        for p in profiles:
            profile_url = p["profile_url"]
            html = html_cache.get(profile_url)
            if html is None:
                try:
                    rp = self._req(used_session, profile_url, limiter=limiter,
                                   verify=used_verify, referer=used_base + "search.do")
                    html = rp.text
                    html_cache.put(profile_url, html)
                except Exception as e:
                    notes.append(f"profile {p['id']}: {type(e).__name__}")
                    continue
            details = self._parse_profile(html, used_base)
            if details.get("lat") is None and details.get("address"):
                details["lat"], details["lon"] = self._geocode(
                    details["address"], geocode, limiter
                )
            offenders.append({**p, **details})

        return FetchResult(
            self.name, "ok",
            f"{len(offenders)} offenders | {'; '.join(notes)}",
            records=offenders,
            meta={"used_params": used_params, "used_base": used_base, "zip": settings.zip},
        )

    def _new_session(self, base: str) -> requests.Session:
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        return s

    def _req(self, session, url, *, params=None, limiter=None, timeout=30,
             verify=True, referer=None):
        if limiter is not None:
            limiter.wait()
        headers = {}
        if referer:
            headers["Referer"] = referer
        return session.get(url, params=params, timeout=timeout, verify=verify,
                           headers=headers, allow_redirects=True)

    def _parse_results(self, html: str, base: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out: list[dict] = []
        for a in soup.select("a[href]"):
            href = a.get("href", "")
            if not href:
                continue
            hl = href.lower()
            if not any(t in hl for t in ["detail", "profile", "offender", "sornum", "id="]):
                continue
            url = urljoin(base, href)
            if not urlparse(url).netloc:
                continue
            m = re.search(r"(?:sorNum|offenderId|id|num)=([A-Za-z0-9_-]+)", href, re.I)
            ofndr_id = m.group(1) if m else url
            name = a.get_text(" ", strip=True)
            if not name or len(name) < 3:
                continue
            if any(x["id"] == ofndr_id for x in out):
                continue
            out.append({"id": str(ofndr_id), "name": name, "profile_url": url})
        return out

    def _parse_profile(self, html: str, base: str) -> dict:
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text("\n", strip=True)
        out: dict = {
            "address": "", "zip_code": "", "offenses": [],
            "last_verified": None, "photo_url": None, "lat": None, "lon": None,
        }
        img = soup.find("img", src=re.compile(r"photo|offender|sor", re.I))
        if img and img.get("src"):
            out["photo_url"] = urljoin(base, img["src"])

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
            import requests as _rq
            r = _rq.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": address, "format": "json", "limit": 1, "countrycodes": "us"},
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=20,
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
