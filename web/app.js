// Paths resolve against whatever directory serves index.html.
// Local dev (python -m http.server from repo root + /web/): falls back to ../data, ../config.
// Pages (deployed as a flat artifact): snapshot.json and zip_20874.geojson sit alongside index.html.
const SNAPSHOT_CANDIDATES = ["./snapshot.json", "../data/snapshot.json"];
const GEO_CANDIDATES = ["./zip_20874.geojson", "../config/zip_20874.geojson"];

async function fetchFirstAvailable(urls, init) {
  for (const u of urls) {
    try {
      const r = await fetch(u, init);
      if (r.ok) return r;
    } catch (_) {}
  }
  throw new Error("no candidate URL returned ok");
}

const SOURCE_COLORS = {
  crime: "#ff9c6a",
  dispatched: "#46d7ff",
  fire_ems: "#ffb300",
  offender: "#b084ff",
};

const state = {
  snapshot: null,
  incidentCluster: null,
  offenderLayer: null,
  incidentMarkers: [],
  offenderMarkers: [],
  lockToMap: false,
  showOffenders: true,
  map: null,
};

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toISOString().replace("T", " ").slice(0, 16) + "Z";
}

function parseIso(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return isNaN(d) ? null : d;
}

function snapshotNow() {
  const snapIso = state.snapshot && state.snapshot.generated_at;
  const d = snapIso ? parseIso(snapIso) : null;
  return d ? d.getTime() : Date.now();
}

function within(iso, hours) {
  if (!hours || hours <= 0) return true;
  const d = parseIso(iso);
  if (!d) return false;
  const delta = snapshotNow() - d.getTime();
  if (delta < 0) return true;
  return delta <= hours * 3600 * 1000;
}

// Bidirectional street-suffix synonyms. We normalize both query and haystack
// to the short form so "Germantown Road" matches "GERMANTOWN RD".
const SUFFIX_MAP = {
  road: "rd", rd: "rd",
  street: "st", st: "st",
  avenue: "ave", ave: "ave", av: "ave",
  drive: "dr", dr: "dr",
  boulevard: "blvd", blvd: "blvd",
  highway: "hwy", hwy: "hwy",
  parkway: "pkwy", pkwy: "pkwy",
  place: "pl", pl: "pl",
  court: "ct", ct: "ct",
  lane: "ln", ln: "ln",
  circle: "cir", cir: "cir",
  terrace: "ter", ter: "ter",
  way: "way",
};

function normalize(s) {
  return (s || "")
    .toLowerCase()
    // strip punctuation (commas, periods, ampersands) to help token matching
    .replace(/[.,&]/g, " ")
    .split(/\s+/)
    .filter(Boolean)
    .map((t) => SUFFIX_MAP[t] || t)
    .join(" ");
}

function tokenize(q) {
  return normalize(q).split(/\s+/).filter(Boolean);
}

function matchesAllTokens(haystack, tokens) {
  if (!tokens.length) return true;
  const hay = normalize(haystack);
  return tokens.every((t) => hay.includes(t));
}

function makeIcon(color, shape = "circle") {
  const svg = shape === "triangle"
    ? `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="20" height="20">
         <polygon points="10,2 18,17 2,17" fill="${color}" stroke="#000" stroke-width="1"/>
       </svg>`
    : `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" width="18" height="18">
         <circle cx="10" cy="10" r="7" fill="${color}" stroke="#000" stroke-width="1.5"/>
       </svg>`;
  return L.divIcon({ className: "pin", html: svg, iconSize: [20, 20], iconAnchor: [10, 10] });
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function byId(id) { return document.getElementById(id); }

function on(id, event, handler) {
  const el = byId(id);
  if (!el) { console.warn(`[app] missing #${id}; skipping ${event} listener`); return; }
  el.addEventListener(event, handler);
}

function renderHeader(snap) {
  document.getElementById("data-as-of").textContent =
    snap.generated_at ? `Data as of ${fmtTime(snap.generated_at)}` : "No data";
  const health = Object.entries(snap.sources || {}).map(([k, v]) =>
    `${k}:${v.status}`).join(" / ");
  document.getElementById("source-health").textContent = health;
}

function renderSourceTallies(incidents) {
  const counts = {};
  (incidents || []).forEach((i) => { counts[i.source] = (counts[i.source] || 0) + 1; });
  document.querySelectorAll(".tally[data-tally]").forEach((el) => {
    const n = counts[el.dataset.tally] || 0;
    el.textContent = `(${n})`;
  });
}

function renderFilterSummary(f, visibleCount) {
  const el = byId("filter-summary");
  if (!el) return;
  const labels = [];
  labels.push(`<strong>${visibleCount}</strong> incidents shown`);
  if (f.hours > 0) labels.push(`last ${f.hours >= 24 ? (f.hours / 24) + "d" : f.hours + "h"}`);
  else labels.push("all time");
  const srcList = [...f.sources];
  if (srcList.length && srcList.length < 3) labels.push(`sources: ${srcList.join(", ")}`);
  if (!srcList.length) labels.push("no sources");
  if (f.tokens.length) labels.push(`search: ${f.tokens.join(" + ")}`);
  el.innerHTML = labels.join(" · ");
}

function renderCategories(incidents) {
  const counts = {};
  incidents.forEach((i) => {
    const c = i.category || "Other";
    counts[c] = (counts[c] || 0) + 1;
  });
  const el = document.getElementById("categories");
  el.innerHTML = "";
  Object.keys(counts).sort().forEach((c) => {
    const wrap = document.createElement("label");
    wrap.innerHTML = `<input type="checkbox" class="cat" value="${escapeHtml(c)}" checked> ${escapeHtml(c)} <span class="tally">(${counts[c]})</span>`;
    el.appendChild(wrap);
  });
}

function currentFilters() {
  const hours = Number(document.getElementById("time-range").value);
  const sources = new Set(
    [...document.querySelectorAll(".src:checked")].map((x) => x.value)
  );
  const allCats = document.querySelectorAll(".cat");
  const categoriesReady = allCats.length > 0;
  const categories = new Set(
    [...document.querySelectorAll(".cat:checked")].map((x) => x.value)
  );
  const q = document.getElementById("q").value;
  const tokens = tokenize(q);
  return { hours, sources, categories, categoriesReady, q, tokens };
}

function incidentHaystack(i) {
  return [i.description, i.address, i.category, i.subcategory, i.source].filter(Boolean).join(" ");
}

function offenderHaystack(o) {
  return [o.name, o.address, (o.offenses || []).join(" "), "offender", "registry"].filter(Boolean).join(" ");
}

function matchesIncident(i, f) {
  if (!f.sources.has(i.source)) return false;
  if (!within(i.occurred_at, f.hours)) return false;
  // No categories selected = show nothing (matches intuitive "None" behavior).
  // Keep the guard only when the category list hasn't been rendered yet.
  if (f.categoriesReady && !f.categories.has(i.category || "Other")) return false;
  return matchesAllTokens(incidentHaystack(i), f.tokens);
}

function visibleIncidents(f) {
  return (state.snapshot.incidents || []).filter((i) => matchesIncident(i, f));
}

function visibleOffenders(f) {
  return (state.snapshot.offenders || []).filter((o) => matchesAllTokens(offenderHaystack(o), f.tokens));
}

function clearLayers() {
  if (state.incidentCluster) state.incidentCluster.clearLayers();
  if (state.offenderLayer) state.offenderLayer.clearLayers();
  state.incidentMarkers = [];
  state.offenderMarkers = [];
}

function renderMarkers(incidents, offenders) {
  clearLayers();

  const incidentMs = [];
  for (const i of incidents) {
    if (i.lat == null || i.lon == null) continue;
    const color = SOURCE_COLORS[i.source] || "#aaa";
    const m = L.marker([i.lat, i.lon], { icon: makeIcon(color) });
    m.bindPopup(popupForIncident(i));
    m.on("click", () => showDetail(detailHtmlForIncident(i)));
    m._incident = i;
    incidentMs.push(m);
    state.incidentMarkers.push(m);
  }
  state.incidentCluster.addLayers(incidentMs);

  if (state.showOffenders) {
    for (const o of offenders) {
      if (o.lat == null || o.lon == null) continue;
      const m = L.marker([o.lat, o.lon], { icon: makeIcon(SOURCE_COLORS.offender, "triangle") });
      m.bindPopup(popupForOffender(o));
      m.on("click", () => showDetail(detailHtmlForOffender(o)));
      m._offender = o;
      state.offenderLayer.addLayer(m);
      state.offenderMarkers.push(m);
    }
  }
}

function popupForIncident(i) {
  return `<strong>${escapeHtml(i.description || "Incident")}</strong><br>
    <span style="color:#8a93a6">${escapeHtml(i.category || "")}${i.subcategory ? " · " + escapeHtml(i.subcategory) : ""}</span><br>
    <span style="color:#8a93a6">${fmtTime(i.occurred_at)}</span><br>
    ${escapeHtml(i.address || "")}<br>
    ${i.raw_url ? `<a href="${i.raw_url}" target="_blank" rel="noopener">source row</a>` : ""}`;
}

function popupForOffender(o) {
  return `<strong>${escapeHtml(o.name)}</strong>
    <span style="background:#2a1d3d;color:#b084ff;font-size:10px;padding:1px 5px;border-radius:3px;margin-left:6px;">REGISTRY</span><br>
    ${escapeHtml(o.address || "")}<br>
    <span style="color:#8a93a6">last verified: ${escapeHtml(o.last_verified || "unknown")}</span><br>
    ${(o.offenses && o.offenses.length) ? `<div style="color:#8a93a6;font-size:11px;margin-top:4px;">${escapeHtml(o.offenses.join("; "))}</div>` : ""}
    ${o.profile_url && o.profile_url !== "#demo" ? `<a href="${o.profile_url}" target="_blank" rel="noopener">registry profile</a>` : ""}`;
}

function renderIncidentList(incidents) {
  const ul = document.getElementById("list");
  ul.innerHTML = "";
  const items = [...incidents].sort((a, b) => {
    const at = parseIso(a.occurred_at)?.getTime() || 0;
    const bt = parseIso(b.occurred_at)?.getTime() || 0;
    return bt - at;
  });
  document.getElementById("list-count").textContent = `(${items.length})`;

  if (items.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No incidents match your filters.";
    ul.appendChild(empty);
    return;
  }

  for (const i of items) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.innerHTML = `
      <div class="row-title"><span class="badge ${i.source}">${escapeHtml(i.source)}</span>${escapeHtml(i.description || "Incident")}</div>
      <div class="row-meta">${escapeHtml(i.category || "")}${i.subcategory ? " · " + escapeHtml(i.subcategory) : ""}</div>
      <div class="row-meta">${fmtTime(i.occurred_at)}</div>
      <div class="row-addr">${escapeHtml(i.address || "")}</div>`;
    btn.addEventListener("click", () => focusIncident(i));
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function renderOffenderList(offenders) {
  const ul = document.getElementById("offender-list");
  ul.innerHTML = "";
  const sorted = [...offenders].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
  document.getElementById("offender-count").textContent = `(${sorted.length})`;

  if (sorted.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "No offenders match your search.";
    ul.appendChild(empty);
    return;
  }

  for (const o of sorted) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    btn.innerHTML = `
      <div class="row-title"><span class="badge offender">registry</span>${escapeHtml(o.name || "")}</div>
      <div class="row-addr">${escapeHtml(o.address || "")}</div>
      <div class="row-meta">last verified: ${escapeHtml(o.last_verified || "unknown")}${o.lat == null ? " · address only" : ""}</div>`;
    btn.addEventListener("click", () => focusOffender(o));
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function openMarker(m, lat, lon) {
  state.map.flyTo([lat, lon], 16, { duration: 0.6 });
  if (!m) return;
  if (state.incidentCluster && state.incidentCluster.hasLayer(m) &&
      typeof state.incidentCluster.zoomToShowLayer === "function") {
    state.incidentCluster.zoomToShowLayer(m, () => m.openPopup());
  } else {
    m.openPopup();
  }
}

function showDetail(html) {
  const lists = byId("lists");
  const detail = byId("detail");
  const body = byId("detail-body");
  if (!lists || !detail || !body) return;
  body.innerHTML = html;
  lists.hidden = true;
  detail.hidden = false;
  detail.scrollTop = 0;
}

function hideDetail() {
  const lists = byId("lists");
  const detail = byId("detail");
  if (!lists || !detail) return;
  lists.hidden = false;
  detail.hidden = true;
}

function kvTable(obj) {
  const rows = Object.entries(obj || {}).map(([k, v]) => {
    const val = v == null ? "—" : (typeof v === "object" ? JSON.stringify(v) : String(v));
    return `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(val)}</td></tr>`;
  });
  return `<table class="kv">${rows.join("")}</table>`;
}

function detailHtmlForIncident(i) {
  const summary = {
    source: i.source,
    category: i.category,
    subcategory: i.subcategory,
    occurred_at: i.occurred_at,
    reported_at: i.reported_at,
    address: i.address,
    zip_code: i.zip_code,
    lat: i.lat,
    lon: i.lon,
  };
  const actions = [];
  if (i.raw_url && i.raw_url !== "#demo") {
    actions.push(`<a href="${i.raw_url}" target="_blank" rel="noopener">Open in MoCo open data portal &rarr;</a>`);
  }
  if (i.lat != null && i.lon != null) {
    actions.push(`<a href="https://www.google.com/maps?q=${i.lat},${i.lon}" target="_blank" rel="noopener">Open in Google Maps &rarr;</a>`);
  }
  return `
    <h3>${escapeHtml(i.description || "Incident")}</h3>
    <div class="subhead">
      <span class="badge ${escapeHtml(i.source)}">${escapeHtml(i.source)}</span>
      ${escapeHtml(i.category || "")}${i.subcategory ? " · " + escapeHtml(i.subcategory) : ""} · ${fmtTime(i.occurred_at)}
    </div>
    <div class="actions">${actions.join("")}</div>
    <div class="section-title">Normalized fields</div>
    ${kvTable(summary)}
    <div class="section-title">All raw fields (${Object.keys(i.raw || {}).length})</div>
    ${kvTable(i.raw || {})}
  `;
}

function detailHtmlForOffender(o) {
  const actions = [];
  if (o.profile_url && o.profile_url !== "#demo") {
    actions.push(`<a href="${o.profile_url}" target="_blank" rel="noopener">Registry profile &rarr;</a>`);
  }
  if (o.lat != null && o.lon != null) {
    actions.push(`<a href="https://www.google.com/maps?q=${o.lat},${o.lon}" target="_blank" rel="noopener">Open in Google Maps &rarr;</a>`);
  }
  return `
    <h3>${escapeHtml(o.name || "Offender")}</h3>
    <div class="subhead">
      <span class="badge offender">registry</span>
      ZIP ${escapeHtml(o.zip_code || "")} · last verified: ${escapeHtml(o.last_verified || "unknown")}
    </div>
    <div class="actions">${actions.join("")}</div>
    <div class="section-title">Record</div>
    ${kvTable({
      name: o.name,
      address: o.address,
      zip_code: o.zip_code,
      last_verified: o.last_verified,
      lat: o.lat,
      lon: o.lon,
      profile_url: o.profile_url,
      offenses: (o.offenses || []).join("; "),
    })}
  `;
}

function focusIncident(i) {
  showDetail(detailHtmlForIncident(i));
  if (i.lat != null) {
    const m = state.incidentMarkers.find((m) => m._incident.id === i.id);
    openMarker(m, i.lat, i.lon);
  }
}

function focusOffender(o) {
  showDetail(detailHtmlForOffender(o));
  if (o.lat != null) {
    const m = state.offenderMarkers.find((m) => m._offender.id === o.id);
    openMarker(m, o.lat, o.lon);
  }
}

function refresh() {
  if (!state.snapshot) return;
  const f = currentFilters();
  let incidents = visibleIncidents(f);
  let offenders = visibleOffenders(f);

  renderMarkers(incidents, offenders);

  if (state.lockToMap) {
    const bounds = state.map.getBounds();
    incidents = incidents.filter((i) => i.lat != null && bounds.contains([i.lat, i.lon]));
    offenders = offenders.filter((o) => o.lat != null && bounds.contains([o.lat, o.lon]));
  }

  renderIncidentList(incidents);
  renderOffenderList(offenders);
  renderFilterSummary(f, incidents.length);

  // Toggle visibility of the "clear search" X (defensive — skip if HTML is stale).
  const qEl = byId("q");
  const qClear = byId("q-clear");
  if (qEl && qClear) qClear.hidden = !qEl.value;
}

async function main() {
  state.map = L.map("map", { zoomControl: true }).setView([39.17, -77.24], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(state.map);

  state.incidentCluster = L.markerClusterGroup({ disableClusteringAtZoom: 15, spiderfyOnMaxZoom: true });
  state.offenderLayer = L.layerGroup();  // offenders stay unclustered for a scannable registry
  state.map.addLayer(state.incidentCluster);
  state.map.addLayer(state.offenderLayer);

  try {
    const geo = await (await fetchFirstAvailable(GEO_CANDIDATES)).json();
    L.geoJSON(geo, { style: { color: "#46d7ff", weight: 1, fillOpacity: 0 } }).addTo(state.map);
  } catch (_) {}

  let snap;
  try {
    snap = await (await fetchFirstAvailable(SNAPSHOT_CANDIDATES, { cache: "no-store" })).json();
  } catch (e) {
    document.getElementById("data-as-of").textContent = "snapshot not available yet";
    return;
  }
  state.snapshot = snap;
  renderHeader(snap);
  renderCategories(snap.incidents || []);
  renderSourceTallies(snap.incidents || []);

  const wireRefresh = (sel) => document.querySelectorAll(sel).forEach((el) => {
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  });
  wireRefresh(".src, #time-range, #q");
  on("categories", "change", refresh);

  document.querySelectorAll(".toggle-row button[data-toggle]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.target;
      const checked = btn.dataset.toggle === "all";
      document.querySelectorAll(target).forEach((cb) => (cb.checked = checked));
      refresh();
    });
  });

  on("q-clear", "click", () => {
    const q = byId("q");
    if (q) { q.value = ""; q.focus(); }
    refresh();
  });
  on("show-offenders", "change", (e) => {
    state.showOffenders = e.target.checked;
    if (!state.showOffenders) state.offenderLayer.clearLayers();
    refresh();
  });
  on("lock-to-map", "change", (e) => {
    state.lockToMap = e.target.checked;
    refresh();
  });
  state.map.on("moveend", () => { if (state.lockToMap) refresh(); });
  on("reset", "click", () => {
    const tr = byId("time-range"); if (tr) tr.value = "168";
    const q = byId("q"); if (q) q.value = "";
    document.querySelectorAll(".src, .cat").forEach((el) => (el.checked = true));
    const so = byId("show-offenders"); if (so) so.checked = true;
    state.showOffenders = true;
    const lm = byId("lock-to-map"); if (lm) lm.checked = false;
    state.lockToMap = false;
    refresh();
  });

  // Enter in the search box triggers refresh explicitly (avoids any implicit
  // form-submit navigation in browsers that wrap lone inputs in a form).
  on("q", "keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); refresh(); }
  });

  on("detail-close", "click", hideDetail);
  // ESC also closes the detail drawer.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideDetail();
  });

  refresh();
}

main();
