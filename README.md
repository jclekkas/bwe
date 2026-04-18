# MoCo 20874 Public Safety

Daily email digest + interactive web explorer for public-safety events in
Montgomery County, Maryland — filtered to ZIP **20874** (Germantown).

- **Data sources**
  - Montgomery County Crime (Socrata `icn6-v9z3`) — filtered by `zip_code`.
  - Police Dispatched Incidents (Socrata `98cc-bc7d`) — filtered by bbox + ZIP polygon.
  - MCFRS Fire/EMS: station-daily aggregates (`v68m-9rt9`) and individual overdoses (`4wcf-kdya`).
  - Maryland Sex Offender Registry via `icrimewatch.net` (scraped, politely).
- **Runtime**: GitHub Actions cron at ~7:15 AM ET.
- **Email**: SMTP (Gmail app password by default).
- **UI**: static HTML + Leaflet, served from GitHub Pages; reads the same
  `data/snapshot.json` the digest was built from.

## Setup

1. **Fork / push the repo.** All development here happens on
   `claude/local-alert-emails-5tQLN`.

2. **Add repo secrets** under _Settings → Secrets and variables → Actions_:

   | Secret | Required | Notes |
   | --- | --- | --- |
   | `SMTP_USER` | yes | Gmail address sending the digest |
   | `SMTP_PASS` | yes | Gmail [app password](https://myaccount.google.com/apppasswords) |
   | `DIGEST_TO` | yes | Your inbox (can be different from `SMTP_USER`) |
   | `SMTP_HOST` | no | defaults to `smtp.gmail.com` |
   | `SMTP_PORT` | no | defaults to `587` |
   | `DIGEST_FROM` | no | defaults to `SMTP_USER` |
   | `SOCRATA_APP_TOKEN` | no | get one at `data.montgomerycountymd.gov` if you see 429s |

3. **Enable Pages** — _Settings → Pages → Source: Deploy from a branch → Branch:
   `claude/local-alert-emails-5tQLN` / folder `/ (root)`_. Then visit:
   `https://<you>.github.io/<repo>/web/`

4. **Run it once** — _Actions → Daily Digest → Run workflow_. Verify:
   - run is green
   - `data/snapshot.json` is updated on the branch
   - email arrives at `DIGEST_TO`
   - the UI shows the new timestamp after Pages rebuilds (1–10 min lag)

5. **(Optional) Replace the ZIP polygon** at `config/zip_20874.geojson`. The
   committed file is a bbox placeholder — for accurate point-in-polygon
   filtering, download the 2020 ZCTA shapefile from the US Census TIGER/Line
   (`https://www.census.gov/cgi-bin/geo/shapefiles/index.php`), filter to
   `GEOID10=20874`, and convert to GeoJSON.

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Fetch live data (writes data/snapshot.json and data/snapshot.meta.json)
PYTHONPATH=src python -m moco_safety fetch --days 7

# Build digest and write HTML preview (no email)
PYTHONPATH=src python -m moco_safety digest --out /tmp/preview.html
open /tmp/preview.html

# Actually send (requires SMTP env vars)
export SMTP_USER=you@gmail.com SMTP_PASS="app-password" DIGEST_TO=you@example.com
PYTHONPATH=src python -m moco_safety digest --send

# Run the UI locally (must serve from repo root so ../data/... resolves)
python -m http.server 8000
# open http://localhost:8000/web/

# Tests
PYTHONPATH=src python -m pytest
```

## Repo layout

```
src/moco_safety/        # Python package: fetchers, normalize, digest, CLI
config/                 # settings, category map, ZIP polygon
data/                   # snapshot.json (committed by the cron), history/
web/                    # static site: index.html, app.js, styles.css
.github/workflows/      # daily-digest.yml
tests/                  # pytest suite (offline, fixtures in tests/fixtures)
```

## Known limitations

- **Socrata lag**: the MoCo Crime dataset typically refreshes on a multi-day
  cadence. A 24-hour window often contains zero rows — that's a publishing
  lag, not an absence of events. The digest shows each source's status and
  most-recent record so you can tell.
- **Fire/EMS granularity**: MCFRS does not publish per-call addresses or
  coordinates on the open data portal, only station-daily aggregates.
  Overdoses (`4wcf-kdya`) are the one granular fire-side source. The UI shows
  station counts in the list only; overdoses get map pins.
- **Sex-offender scraping is fragile**: `icrimewatch.net` has no public API,
  so if they change their HTML the parser will break. When the fetch errors,
  the snapshot preserves the previous list as `offenders_stale_copy` so the
  UI doesn't go blank, and a tracking GitHub issue opens automatically.
- **Pages eventual consistency**: Pages usually takes 1–10 minutes to publish
  after the cron commits. The UI header shows `generated_at` so staleness is
  visible.
- **DST drift**: Actions cron is UTC-only. The 11:15 UTC schedule lands at
  ~7:15 AM ET during EDT and ~6:15 AM ET during EST. Acceptable 1 h drift.
- **Privacy**: the Pages URL is public. Anyone who finds it can see the
  addresses of crime incidents and offenders. This is personal-use "privacy
  via obscurity" — do not share the URL publicly.

## Troubleshooting

- **No email arriving**: check the Actions run → "Build + send digest" step.
  A missing secret raises `required env var X is not set`. Gmail blocks sign-ins
  from "less secure apps" — you must use an app password, not your real password.
- **`zip_code` filter returns nothing**: some MoCo records have `zip_code` as
  an integer. If that ever bites, change the where clause in
  `src/moco_safety/fetchers/crime.py` to `zip_code='20874' OR zip_code=20874`.
- **Dispatched incidents empty**: the Socrata geo column is sometimes called
  `location` and sometimes `geolocation`. The fetcher already tries
  `within_box(location, ...)` and falls back to lat/lon bbox; if both fail,
  inspect a sample record from `https://data.montgomerycountymd.gov/resource/98cc-bc7d.json?$limit=1`.
- **UI shows "snapshot not available yet"**: the cron hasn't run yet or Pages
  hasn't picked up the commit. Run the workflow manually and wait a few
  minutes.
