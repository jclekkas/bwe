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
  markers: null,
  incidentMarkers: [],
  offenderMarkers: [],
  lockToMap: false,
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
  // Anchor "now" to the snapshot's generated_at so filters work even if the
  // viewer's clock is far from when the data was collected.
  const snapIso = state.snapshot && state.snapshot.generated_at;
  const d = snapIso ? parseIso(snapIso) : null;
  return d ? d.getTime() : Date.now();
}

function within(iso, hours) {
  if (!hours || hours <= 0) return true;
  const d = parseIso(iso);
  if (!d) return false;
  const anchor = snapshotNow();
  const delta = anchor - d.getTime();
  // Negative delta means the record is dated after the snapshot was built —
  // should not happen in real data but treat it as "now" so it isn't silently dropped.
  if (delta < 0) return true;
  return delta <= hours * 3600 * 1000;
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

function renderHeader(snap) {
  document.getElementById("data-as-of").textContent =
    snap.generated_at ? `Data as of ${fmtTime(snap.generated_at)}` : "No data";
  const health = Object.entries(snap.sources || {}).map(([k, v]) =>
    `${k}:${v.status}`).join(" / ");
  document.getElementById("source-health").textContent = health;
}

function renderCategories(incidents) {
  const cats = new Set();
  incidents.forEach((i) => cats.add(i.category || "Other"));
  const el = document.getElementById("categories");
  el.innerHTML = "";
  [...cats].sort().forEach((c) => {
    const id = `cat-${c.replace(/\s+/g, "_")}`;
    const wrap = document.createElement("label");
    wrap.innerHTML = `<input type="checkbox" class="cat" value="${c}" checked> ${c}`;
    el.appendChild(wrap);
  });
}

function currentFilters() {
  const hours = Number(document.getElementById("time-range").value);
  const sources = new Set(
    [...document.querySelectorAll(".src:checked")].map((x) => x.value)
  );
  const categories = new Set(
    [...document.querySelectorAll(".cat:checked")].map((x) => x.value)
  );
  const q = document.getElementById("q").value.trim().toLowerCase();
  return { hours, sources, categories, q };
}

function matches(incident, f) {
  if (!f.sources.has(incident.source)) return false;
  if (!within(incident.occurred_at, f.hours)) return false;
  if (f.categories.size && !f.categories.has(incident.category)) return false;
  if (f.q) {
    const hay = [
      incident.description,
      incident.address,
      incident.category,
      incident.subcategory,
      incident.source,
    ].filter(Boolean).join(" ").toLowerCase();
    if (!hay.includes(f.q)) return false;
  }
  return true;
}

function visibleIncidents(f) {
  const snap = state.snapshot;
  const incidents = (snap.incidents || []).filter((i) => matches(i, f));
  const offenders = f.sources.has("offenders")
    ? (snap.offenders || []).filter((o) => {
        if (!f.q) return true;
        const hay = [o.name, o.address, (o.offenses || []).join(" "), "offender"]
          .filter(Boolean).join(" ").toLowerCase();
        return hay.includes(f.q);
      })
    : [];
  return { incidents, offenders };
}

function renderList(incidents, offenders) {
  const ul = document.getElementById("list");
  ul.innerHTML = "";
  const items = [
    ...incidents.map((i) => ({ type: "incident", data: i, t: parseIso(i.occurred_at)?.getTime() || 0 })),
    ...offenders.map((o) => ({ type: "offender", data: o, t: 0 })),
  ].sort((a, b) => b.t - a.t);

  document.getElementById("list-count").textContent = `(${items.length})`;

  if (items.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "Nothing matches your filters.";
    ul.appendChild(empty);
  }

  for (const it of items) {
    const li = document.createElement("li");
    const btn = document.createElement("button");
    if (it.type === "incident") {
      const i = it.data;
      btn.innerHTML = `
        <div class="row-title"><span class="badge ${i.source}">${i.source}</span>${escapeHtml(i.description || "Incident")}</div>
        <div class="row-meta">${escapeHtml(i.category || "")}${i.subcategory ? " · " + escapeHtml(i.subcategory) : ""}</div>
        <div class="row-meta">${fmtTime(i.occurred_at)}</div>
        <div class="row-addr">${escapeHtml(i.address || "")}</div>`;
      btn.addEventListener("click", () => focusIncident(i));
    } else {
      const o = it.data;
      btn.innerHTML = `
        <div class="row-title"><span class="badge offender">offender</span>${escapeHtml(o.name || "")}</div>
        <div class="row-addr">${escapeHtml(o.address || "")}</div>
        <div class="row-meta">last verified: ${escapeHtml(o.last_verified || "unknown")}</div>`;
      btn.addEventListener("click", () => focusOffender(o));
    }
    li.appendChild(btn);
    ul.appendChild(li);
  }
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function clearMarkers() {
  if (state.markers) state.markers.clearLayers();
  state.incidentMarkers = [];
  state.offenderMarkers = [];
}

function renderMarkers(incidents, offenders) {
  clearMarkers();
  const ms = [];
  for (const i of incidents) {
    if (i.lat == null || i.lon == null) continue;
    const color = SOURCE_COLORS[i.source] || "#aaa";
    const m = L.marker([i.lat, i.lon], { icon: makeIcon(color) });
    m.bindPopup(popupForIncident(i));
    m._incident = i;
    ms.push(m);
    state.incidentMarkers.push(m);
  }
  for (const o of offenders) {
    if (o.lat == null || o.lon == null) continue;
    const m = L.marker([o.lat, o.lon], { icon: makeIcon(SOURCE_COLORS.offender, "triangle") });
    m.bindPopup(popupForOffender(o));
    m._offender = o;
    ms.push(m);
    state.offenderMarkers.push(m);
  }
  state.markers.addLayers(ms);
}

function popupForIncident(i) {
  return `<strong>${escapeHtml(i.description || "Incident")}</strong><br>
    <span style="color:#8a93a6">${escapeHtml(i.category || "")}${i.subcategory ? " · " + escapeHtml(i.subcategory) : ""}</span><br>
    <span style="color:#8a93a6">${fmtTime(i.occurred_at)}</span><br>
    ${escapeHtml(i.address || "")}<br>
    ${i.raw_url ? `<a href="${i.raw_url}" target="_blank" rel="noopener">source row</a>` : ""}`;
}

function popupForOffender(o) {
  return `<strong>${escapeHtml(o.name)}</strong><br>
    ${escapeHtml(o.address || "")}<br>
    <span style="color:#8a93a6">last verified: ${escapeHtml(o.last_verified || "unknown")}</span><br>
    ${o.profile_url ? `<a href="${o.profile_url}" target="_blank" rel="noopener">profile</a>` : ""}`;
}

function openMarker(m, lat, lon) {
  // zoomToShowLayer uncluster first, then open the popup inside the callback.
  state.map.flyTo([lat, lon], 16, { duration: 0.6 });
  if (!m) return;
  if (state.markers && typeof state.markers.zoomToShowLayer === "function") {
    state.markers.zoomToShowLayer(m, () => m.openPopup());
  } else {
    m.openPopup();
  }
}

function focusIncident(i) {
  if (i.lat == null) return;
  const m = state.incidentMarkers.find((m) => m._incident.id === i.id);
  openMarker(m, i.lat, i.lon);
}

function focusOffender(o) {
  if (o.lat == null) return;
  const m = state.offenderMarkers.find((m) => m._offender.id === o.id);
  openMarker(m, o.lat, o.lon);
}

function refresh() {
  const f = currentFilters();
  let { incidents, offenders } = visibleIncidents(f);
  renderMarkers(incidents, offenders);
  if (state.lockToMap) {
    const bounds = state.map.getBounds();
    incidents = incidents.filter((i) => i.lat != null && bounds.contains([i.lat, i.lon]));
    offenders = offenders.filter((o) => o.lat != null && bounds.contains([o.lat, o.lon]));
  }
  renderList(incidents, offenders);
}

async function main() {
  state.map = L.map("map", { zoomControl: true }).setView([39.17, -77.24], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "&copy; OpenStreetMap contributors",
    maxZoom: 19,
  }).addTo(state.map);

  state.markers = L.markerClusterGroup({ disableClusteringAtZoom: 15, spiderfyOnMaxZoom: true });
  state.map.addLayer(state.markers);

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

  document.querySelectorAll(".src, #time-range, #q").forEach((el) => {
    el.addEventListener("input", refresh);
    el.addEventListener("change", refresh);
  });
  document.getElementById("categories").addEventListener("change", refresh);
  document.getElementById("lock-to-map").addEventListener("change", (e) => {
    state.lockToMap = e.target.checked;
    refresh();
  });
  state.map.on("moveend", () => { if (state.lockToMap) refresh(); });
  document.getElementById("reset").addEventListener("click", () => {
    document.getElementById("time-range").value = "168";
    document.getElementById("q").value = "";
    document.querySelectorAll(".src, .cat").forEach((el) => (el.checked = true));
    document.getElementById("lock-to-map").checked = false;
    state.lockToMap = false;
    refresh();
  });

  refresh();
}

main();
