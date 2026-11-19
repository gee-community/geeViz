// Where a Chart area comes from: Draw (click the map to add points,
// double-click to finish), Map view (the current bounds, charted again
// when the map rests after moving), Upload (a .zip shapefile, .geojson,
// .json, .kmz or .kml file) and Select (the features picked from select
// layers). Ports of lcms-viewer 5chart-manager.js startUserDefinedAreaCharting
// and chartUserDefinedArea, area-charting.js startAutoCharting and
// chartMapExtent, runShpDefinedCharting with 4map-manager.js
// convertToGeoJSON, and the select tool's "Chart Selected Areas".
//
// The parsing helpers at the top are pure; createAreaSources wires the map.
import { smartToFixed } from "../util.js";
import { chartJobs } from "./areachart.js";

// port of 2templates.js #areaUpload accept
export const UPLOAD_ACCEPT = ".zip,.geojson,.json,.kmz,.kml";
// port of 4map-manager.js convertToGeoJSON: shapefiles and KMZ are converted by ogre
export const CONVERT_URL = "https://ogre.adc4gis.com/convert";
// port of area-charting.js startAutoCharting idleDelay
export const IDLE_DELAY = 2000;

export function uploadKind(name) {
  const ext = String(name || "").toLowerCase().split(".").pop();
  if (ext === "geojson" || ext === "json") return "geojson";
  if (ext === "kml") return "kml";
  if (ext === "zip" || ext === "kmz") return "convert";
  return null;
}

const POLY_TYPES = ["Polygon", "MultiPolygon"];

// Polygon features from a GeoJSON FeatureCollection, Feature or geometry.
export function featuresFromGeoJSON(gj) {
  if (!gj || typeof gj !== "object") return [];
  let feats;
  if (gj.type === "FeatureCollection") feats = gj.features || [];
  else if (gj.type === "Feature") feats = [gj];
  else if (gj.type === "GeometryCollection") feats = (gj.geometries || []).map((geometry) => ({ type: "Feature", properties: {}, geometry }));
  else feats = [{ type: "Feature", properties: {}, geometry: gj }];
  return feats
    .filter((f) => f && f.geometry && POLY_TYPES.indexOf(f.geometry.type) > -1)
    .map((f) => ({ type: "Feature", properties: f.properties || {}, geometry: f.geometry }));
}

// port of 5chart-manager.js fixGeoJSONZ (one feature)
export function dropZ(f) {
  const g = f.geometry;
  const ring = (r) => r.map((c) => c.slice(0, 2));
  const coordinates = g.type === "MultiPolygon" ? g.coordinates.map((p) => p.map(ring)) : g.coordinates.map(ring);
  return { ...f, geometry: { ...g, coordinates } };
}

const between = (s, tag) => {
  const out = [];
  const re = new RegExp(`<(?:\\w+:)?${tag}\\b[^>]*>([\\s\\S]*?)</(?:\\w+:)?${tag}>`, "g");
  let m;
  while ((m = re.exec(s))) out.push(m[1]);
  return out;
};
const ringOf = (text) =>
  text
    .trim()
    .split(/\s+/)
    .filter((t) => t)
    .map((t) => t.split(",").slice(0, 2).map(Number));

// Polygon features from KML text: every Polygon's outer and inner rings.
export function featuresFromKml(text) {
  const feats = [];
  between(String(text), "Polygon").forEach((poly) => {
    const outer = between(poly, "outerBoundaryIs").flatMap((b) => between(b, "coordinates"));
    if (!outer.length) return;
    const inner = between(poly, "innerBoundaryIs").flatMap((b) => between(b, "coordinates"));
    feats.push({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [ringOf(outer[0])].concat(inner.map(ringOf)) } });
  });
  return feats;
}

const outerRings = (features) =>
  features.flatMap((f) => (f.geometry.type === "MultiPolygon" ? f.geometry.coordinates.map((p) => p[0]) : [f.geometry.coordinates[0]]));

export function ringBounds(features) {
  const pts = outerRings(features).flat();
  return {
    west: Math.min(...pts.map((p) => p[0])),
    south: Math.min(...pts.map((p) => p[1])),
    east: Math.max(...pts.map((p) => p[0])),
    north: Math.max(...pts.map((p) => p[1])),
  };
}

// port of area-charting.js chartMapExtent's name (getMapExtentCoordsStr order)
export function viewLabel(b, proportion = 0.25, precision = 3) {
  const n = [b.west, b.north, b.east, b.south].map((v) => smartToFixed(v, proportion, precision));
  return `Map view (${n.join(", ")})`;
}

// The map side. opts: ee, google, notify(msg), colors() -> {stroke},
// query() -> the query tool (for selections), idleDelay.
export function createAreaSources(engine, store, charter, opts = {}) {
  const g = opts.google || window.google.maps;
  const ee = opts.ee || window.ee;
  const gmap = engine.gmap;
  const notify = opts.notify || (() => {});
  const colors = opts.colors || (() => ({ stroke: "#e2602a" }));
  const idleDelay = opts.idleDelay === undefined ? IDLE_DELAY : opts.idleDelay;
  const spherical = () => g.geometry && g.geometry.spherical;
  const picking = () => (engine.isPicking ? engine.isPicking() : false);
  const active = (src) => {
    const s = store.get();
    return s.tool === "chart" && (!src || s.areaFrom === src);
  };

  let path = null; // the polyline being drawn
  let shape = null; // the finished polygon
  const uploaded = new g.Data({ map: gmap });
  let last = null; // the area last charted: {geometry, label, extra}
  let viewStr = null;
  let idleId = 0;

  const lineStyle = () => ({ strokeColor: colors().stroke, strokeOpacity: 1, strokeWeight: 3, fillColor: colors().stroke, fillOpacity: 0.12, clickable: false, geodesic: true, zIndex: 3100 });
  function restyle() {
    if (path) path.setOptions(lineStyle());
    if (shape) shape.setOptions(lineStyle());
    const st = lineStyle();
    uploaded.setStyle({ strokeColor: st.strokeColor, strokeWeight: 3, fillColor: st.fillColor, fillOpacity: st.fillOpacity, clickable: false, zIndex: 3100 });
  }
  restyle();

  function clearShapes() {
    if (path) path.setMap(null);
    if (shape) shape.setMap(null);
    path = shape = null;
    uploaded.forEach((f) => uploaded.remove(f));
  }

  function run(area) {
    if (!area) return null;
    last = area;
    return charter.chartArea(area.geometry, area.label, area.extra);
  }

  // ---- Draw ----
  const ll = (p) => [p.lng(), p.lat()];
  gmap.addListener("click", (ev) => {
    if (!ev.latLng || picking() || !active("draw")) return;
    if (shape) {
      shape.setMap(null);
      shape = null;
    }
    if (!path) path = new g.Polyline({ ...lineStyle(), map: gmap });
    const pts = path.getPath();
    const prev = pts.getLength() ? pts.getAt(pts.getLength() - 1) : null;
    // the second click of a double-click lands on the point just added
    if (prev && Math.abs(prev.lat() - ev.latLng.lat()) < 1e-9 && Math.abs(prev.lng() - ev.latLng.lng()) < 1e-9) return;
    pts.push(ev.latLng);
  });
  gmap.addListener("dblclick", (ev) => {
    if (picking() || !active("draw") || !path) return;
    if (ev && ev.stop) ev.stop();
    finishDrawing();
  });
  function finishDrawing() {
    if (!path) return null;
    const pts = path.getPath().getArray();
    if (pts.length < 3) {
      notify("Please draw a polygon on the map: click to add points, double-click to finish.");
      return null;
    }
    path.setMap(null);
    path = null;
    shape = new g.Polygon({ ...lineStyle(), paths: pts, map: gmap });
    const ring = pts.map(ll);
    ring.push(ring[0].slice());
    const areaM2 = spherical() ? spherical().computeArea(pts) : null;
    return run({ geometry: ee.Geometry.Polygon([ring]), label: "Drawn area", extra: { source: "draw", areaM2, ring } });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && path && active("draw")) {
      path.setMap(null);
      path = null;
    }
  });

  // ---- Map view ----
  function viewArea() {
    const b = gmap.getBounds && gmap.getBounds();
    if (!b) return null;
    const j = b.toJSON();
    const bounds = { west: j.west, south: j.south, east: j.east, north: j.north };
    const corners = [
      { lat: j.south, lng: j.west },
      { lat: j.south, lng: j.east },
      { lat: j.north, lng: j.east },
      { lat: j.north, lng: j.west },
    ].map((p) => new g.LatLng(p.lat, p.lng));
    return {
      geometry: ee.Geometry.Rectangle([j.west, j.south, j.east, j.north], null, false),
      label: viewLabel(bounds),
      extra: { source: "view", bounds, areaM2: spherical() ? spherical().computeArea(corners) : null },
    };
  }
  function chartView() {
    const a = viewArea();
    if (!a) return null;
    viewStr = a.label;
    return run(a);
  }
  gmap.addListener("idle", () => {
    if (!active("view")) return;
    const a = viewArea();
    if (!a || a.label === viewStr) return;
    // port of startAutoCharting: clear, then chart once the map rests
    viewStr = a.label;
    charter.cancel();
    store.set({ results: [], where: a.label }, "chart-view-moved");
    const id = ++idleId;
    setTimeout(() => {
      if (id === idleId && active("view")) chartView();
    }, idleDelay);
  });

  // ---- Upload ----
  async function readFeatures(file) {
    const kind = uploadKind(file.name);
    if (kind === "geojson") return featuresFromGeoJSON(JSON.parse(await file.text()));
    if (kind === "kml") return featuresFromKml(await file.text());
    if (kind === "convert") {
      const data = new FormData();
      data.append("targetSrs", "EPSG:4326");
      data.append("upload", file);
      const res = await fetch(CONVERT_URL, { method: "POST", body: data });
      if (!res.ok) throw new Error(`The file could not be converted (${res.status})`);
      return featuresFromGeoJSON(await res.json());
    }
    throw new Error("Please select a .zip shapefile, .geojson, .json, .kml or .kmz file to summarize across");
  }
  function ringArea(r) {
    return spherical() ? spherical().computeArea(r.map((c) => new g.LatLng(c[1], c[0]))) : 0;
  }
  function featureArea(f) {
    const polys = f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates];
    return polys.reduce((a, p) => a + ringArea(p[0]) - p.slice(1).reduce((b, h) => b + ringArea(h), 0), 0);
  }
  async function upload(file) {
    if (!file) return null;
    let features;
    try {
      features = (await readFeatures(file)).map(dropZ);
    } catch (e) {
      notify("Error ingesting study area: " + (e && e.message ? e.message : e));
      return null;
    }
    if (!features.length) {
      notify(`Found 0 polygons in ${file.name}. Please select a file with features.`);
      return null;
    }
    clearShapes();
    uploaded.addGeoJson({ type: "FeatureCollection", features });
    // port of runShpDefinedCharting: each feature dissolved, then charted as one area
    const fc = ee.FeatureCollection(features.map((f) => ee.Feature(f).dissolve(100, ee.Projection("EPSG:4326"))));
    const b = ringBounds(features);
    await new Promise((resolve) => {
      let done = false;
      const finish = () => {
        if (done) return;
        done = true;
        resolve();
      };
      g.event.addListenerOnce(gmap, "idle", finish);
      setTimeout(finish, 2500);
      gmap.fitBounds({ west: b.west, south: b.south, east: b.east, north: b.north });
    });
    const name = file.name.replace(/\.[^.]*$/, "");
    const areaM2 = features.reduce((a, f) => a + featureArea(f), 0);
    return run({ geometry: fc, label: name, extra: { source: "upload", areaM2, features } });
  }

  // ---- Select ----
  async function chartSelection() {
    const sel = store.get().selections || [];
    const q = opts.query && opts.query();
    if (!sel.length || !q) {
      notify("Click features of a select layer on the map first, then chart them.");
      return null;
    }
    const fc = await q.selectionCollection();
    const areaM2 = sel.every((x) => x.areaM2 !== null && x.areaM2 !== undefined) ? sel.reduce((a, x) => a + x.areaM2, 0) : null;
    return run({ geometry: fc, label: sel.map((x) => x.label).join(", "), extra: { source: "select", areaM2 } });
  }

  // ---- reacting to the store ----
  const cursor = () => gmap.setOptions({ draggableCursor: active("draw") ? "crosshair" : null });
  let source = store.get().tool === "chart" ? store.get().areaFrom : null;
  function sourceChanged() {
    const s = store.get();
    const now = s.tool === "chart" ? s.areaFrom : null;
    cursor();
    if (now === source) return;
    source = now;
    clearShapes();
    last = null;
    viewStr = null;
    idleId++;
    charter.cancel();
    if (now) store.set({ results: [], where: "", chartArea: null }, "chart-source");
    if (now === "view") chartView();
  }
  store.on("change:tool", sourceChanged);
  store.on("change:areaFrom", sourceChanged);

  // A layer turned on or off, or a settings change, charts the same area again
  // (port of timeLapseCheckbox's chartMapExtent); cached layers cost nothing.
  const jobSig = () => {
    const s = store.get();
    return chartJobs(s).map((j) => j.layer.id + ":" + j.kind).join(",") + "|" + JSON.stringify(s.chartPeriods);
  };
  let sig = jobSig();
  let again = null;
  const maybeAgain = (value, state, reason) => {
    const next = jobSig();
    // periods filled in from the layers' years while charting are already in use
    if (reason === "chart-periods-auto") {
      sig = next;
      return;
    }
    if (next === sig) return;
    sig = next;
    if (!last || !active()) return;
    clearTimeout(again);
    again = setTimeout(() => last && active() && run(last), 300);
  };
  ["change:layers", "change:order", "change:chartChoices", "change:chartPeriods"].forEach((e) => store.on(e, maybeAgain));
  if (source === "view") chartView();

  return { upload, chartSelection, chartView, finishDrawing, restyle, clearShapes, last: () => last };
}
