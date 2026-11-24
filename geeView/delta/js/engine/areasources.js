// Where a Chart area comes from: Draw (click the map to add points,
// double-click to finish), Map view (the current bounds, charted again
// when the map rests after moving), Upload (a .zip shapefile, .kml, .kmz,
// .gpkg, .gpx, .fgb, .geojson or .json file) and Select (the features picked from select
// layers). Ports of lcms-viewer 5chart-manager.js startUserDefinedAreaCharting
// and chartUserDefinedArea, area-charting.js startAutoCharting and
// chartMapExtent, runShpDefinedCharting with 4map-manager.js
// convertToGeoJSON, and the select tool's "Chart Selected Areas".
//
// The parsing helpers at the top are pure; createAreaSources wires the map.
import { smartToFixed } from "../util.js";
import { zipStore } from "./zip.js";
import { lazyEE } from "./ee.js";
import { chartJobs } from "./areachart.js";
import { drawStyle } from "./drawing.js";
import { createSketch } from "./sketch.js";

// The original's #areaUpload types plus the other vector formats the converter reads.
// A shapefile can also be picked as its parts, without a .zip: they are
// zipped here and sent like a .zip.
export const UPLOAD_ACCEPT = ".zip,.shp,.shx,.dbf,.prj,.cpg,.kml,.kmz,.gpkg,.gpx,.fgb,.geojson,.json";
// The parts a shapefile may come with (as the converter's sidecars).
export const SHAPEFILE_PARTS = [".shp", ".shx", ".dbf", ".prj", ".cpg", ".sbn", ".sbx", ".qix", ".xml"];

const extOf = (n) => {
  const i = String(n).lastIndexOf(".");
  return i < 0 ? "" : String(n).slice(i).toLowerCase();
};
const stemOf = (n) => {
  const i = String(n).lastIndexOf(".");
  return i < 0 ? String(n) : String(n).slice(0, i);
};

// shapefileSets(names): the shapefiles among picked file names, by their
// .shp's name without extension, or the reason they cannot be sent: a part
// missing (named), a part with no .shp, or a file that is not a shapefile part.
export function shapefileSets(names) {
  const list = names.map(String);
  const other = list.find((n) => SHAPEFILE_PARTS.indexOf(extOf(n)) < 0);
  if (other) return { sets: [], error: `${other} is not part of a shapefile. Choose one file at a time, or a shapefile's .shp with its .shx, .dbf and .prj.` };
  const shps = list.filter((n) => extOf(n) === ".shp").map(stemOf);
  if (!shps.length) return { sets: [], error: "Choose the shapefile's .shp along with its .shx, .dbf and .prj." };
  const have = new Set(list.map((n) => n.toLowerCase()));
  for (const s of shps) {
    for (const side of [".shx", ".dbf"]) {
      if (!have.has((s + side).toLowerCase())) return { sets: [], error: `${s}${side} is missing. Choose ${s}.shp with its .shx, .dbf and .prj.` };
    }
  }
  const stems = new Set(shps.map((s) => s.toLowerCase()));
  const stray = list.find((n) => !stems.has(stemOf(n).toLowerCase()));
  if (stray) return { sets: [], error: `${stray} has no ${stemOf(stray)}.shp among the files chosen.` };
  return { sets: shps, error: null };
}
// Files that are not GeoJSON are converted by the geeViz server that serves
// this page (geeViz.eeAuth.vector_convert, at <proxy>/convert/vector), never
// by a third party. The original sent them to ogre.adc4gis.com.
export function convertUrl(proxyBase, origin) {
  const base = String(proxyBase || "").replace(/\/+$/, "") || String(origin || "").replace(/\/+$/, "") + "/ee-api";
  return base + "/convert/vector";
}
// port of area-charting.js startAutoCharting idleDelay
export const IDLE_DELAY = 2000;

export function uploadKind(name) {
  const ext = String(name || "").toLowerCase().split(".").pop();
  if (ext === "geojson" || ext === "json") return "geojson";
  if (["zip", "kml", "kmz", "gpkg", "gpx", "fgb"].indexOf(ext) > -1) return "convert";
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
  const ee = opts.ee || lazyEE;
  // Earth Engine loads on demand: an area waits for it before its Earth
  // Engine geometry is made (the map can rest, and auto charting start,
  // before it has loaded). ready() returns a promise, or nothing when ready.
  const ready = opts.ready || (() => null);
  async function eeWait() {
    const wait = ready();
    if (!wait) return true;
    try {
      await wait;
      return true;
    } catch (e) {
      return false; // Earth Engine did not start; that was reported
    }
  }
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

  let sketch = null; // the Draw source's polygons (engine/sketch.js), made below
  const uploaded = new g.Data({ map: gmap });
  let last = null; // the area last charted: {geometry, label, extra}
  // Uploads and selections wait on the network: each takes a token, and a
  // source or tool change in the meantime makes it stale.
  let opSeq = 0;
  function opToken(src) {
    const id = ++opSeq;
    return () => id === opSeq && active(src);
  }
  let viewStr = null;
  let idleId = 0;

  const lineStyle = () => drawStyle(colors().stroke);
  function restyle() {
    if (sketch) sketch.restyle();
    const st = lineStyle();
    uploaded.setStyle({ strokeColor: st.strokeColor, strokeWeight: 3, fillColor: st.fillColor, fillOpacity: st.fillOpacity, clickable: false, zIndex: 3100 });
  }
  restyle();

  function clearShapes() {
    if (sketch) sketch.reset();
    uploaded.forEach((f) => uploaded.remove(f));
  }

  // area.geometry may be a function that makes it: called once Earth Engine is ready.
  function run(area) {
    if (!area) return null;
    const go = () => {
      const geometry = typeof area.geometry === "function" ? area.geometry() : area.geometry;
      last = { ...area, geometry };
      return charter.chartArea(geometry, area.label, area.extra);
    };
    if (!ready()) return go();
    return eeWait().then((ok) => (ok ? go() : null));
  }

  // ---- Draw ----
  // port of startUserDefinedAreaCharting: double-click finishes a polygon,
  // the next click starts another, and every finished polygon is charted as
  // one area. Undo/redo, Delete and vertex editing come from the sketch; a
  // change to the finished polygons charts again (an edit after a short rest).
  let drawnSig = "[]";
  let editTimer = 0;
  const EDIT_DELAY = opts.editDelay === undefined ? 600 : opts.editDelay;
  function drawnRings() {
    return sketch.paths(false).map((pts) => {
      const ring = pts.map((p) => [p.lng(), p.lat()]);
      ring.push(ring[0].slice());
      return ring;
    });
  }
  function chartDrawn() {
    const paths = sketch.paths(false);
    if (!paths.length) return null;
    const rings = drawnRings();
    const areaM2 = spherical() ? paths.reduce((a, p) => a + spherical().computeArea(p), 0) : null;
    const geometry = () => (rings.length === 1 ? ee.Geometry.Polygon([rings[0]]) : ee.Geometry.MultiPolygon(rings.map((r) => [r])));
    const label = rings.length === 1 ? "Drawn area" : "Drawn areas (" + rings.length + ")";
    return run({ geometry, label, extra: { source: "draw", areaM2, rings } });
  }
  let drawnRun = null;
  function drawnChanged(why) {
    const sig = JSON.stringify(sketch.state().open ? sketch.state().shapes.slice(0, -1) : sketch.state().shapes);
    if (sig === drawnSig) return;
    drawnSig = sig;
    clearTimeout(editTimer);
    if (sig === "[]") {
      // nothing left to chart
      charter.cancel();
      last = null;
      store.set({ results: [], where: "", chartArea: null }, "chart-draw-cleared");
      return;
    }
    if (why === "edit") editTimer = setTimeout(() => active("draw") && chartDrawn(), EDIT_DELAY);
    else drawnRun = chartDrawn();
  }
  sketch = createSketch({
    google: g,
    gmap,
    polygon: true,
    multi: true,
    active: () => active("draw"),
    picking,
    color: () => colors().stroke,
    tooFew: () => notify("Please draw a polygon on the map: click to add points, double-click to finish."),
    onChange: (state, hover, why, status) => {
      store.set({ sketch: { tool: "chart", ...status } }, "sketch");
      if (why === "reset") {
        drawnSig = "[]";
        clearTimeout(editTimer);
        return;
      }
      if (why !== "hover" && why !== "point") drawnChanged(why);
    },
  });
  // Finish the polygon being drawn (as a double-click does); the chart run, or null.
  function finishDrawing() {
    drawnRun = null;
    return sketch.finish() ? drawnRun : null;
  }

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
      geometry: () => ee.Geometry.Rectangle([j.west, j.south, j.east, j.north], null, false),
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
    if (kind === "convert") {
      const data = new FormData();
      data.append("file", file);
      const url = convertUrl(opts.proxyBase ? opts.proxyBase() : "", location.origin);
      const res = await fetch(url, { method: "POST", body: data, credentials: "same-origin" });
      let body = null;
      try {
        body = await res.json();
      } catch (e) {
        body = null;
      }
      if (!res.ok) {
        const why = body && body.error ? body.error + (body.hint ? ". " + body.hint : "") : `The file could not be converted (${res.status})`;
        throw new Error(why);
      }
      return featuresFromGeoJSON(body);
    }
    throw new Error("Please select a shapefile (a .zip, or its .shp, .shx, .dbf and .prj together), .kml, .kmz, .gpkg, .gpx, .fgb, .geojson or .json file to summarize across");
  }
  // A shapefile picked as its parts, zipped into one .zip named for it.
  async function zipShapefile(files) {
    const { sets, error } = shapefileSets(files.map((f) => f.name));
    if (error) throw new Error(error);
    const entries = await Promise.all(files.map(async (f) => ({ name: f.name, bytes: new Uint8Array(await f.arrayBuffer()) })));
    return new File([zipStore(entries)], sets[0] + ".zip", { type: "application/zip" });
  }
  function ringArea(r) {
    return spherical() ? spherical().computeArea(r.map((c) => new g.LatLng(c[1], c[0]))) : 0;
  }
  function featureArea(f) {
    const polys = f.geometry.type === "MultiPolygon" ? f.geometry.coordinates : [f.geometry.coordinates];
    return polys.reduce((a, p) => a + ringArea(p[0]) - p.slice(1).reduce((b, h) => b + ringArea(h), 0), 0);
  }
  // upload(file or [files]): one file, or a shapefile's parts picked together.
  async function upload(picked) {
    const files = (Array.isArray(picked) ? picked : [picked]).filter(Boolean);
    if (!files.length) return null;
    const still = opToken("upload");
    let file = files[0];
    let features;
    try {
      if (files.length > 1 || extOf(file.name) === ".shp") file = await zipShapefile(files);
      features = (await readFeatures(file)).map(dropZ);
      if (!still()) return null;
    } catch (e) {
      if (!still()) return null;
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
    // only the geometry goes to Earth Engine, not the file's properties
    const fc = () => ee.FeatureCollection(features.map((f) => ee.Feature(f.geometry).dissolve(100, ee.Projection("EPSG:4326"))));
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
    if (!still()) return null;
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
    const still = opToken("select");
    const fc = await q.selectionCollection();
    if (!still()) return null;
    const areaM2 = sel.every((x) => x.areaM2 !== null && x.areaM2 !== undefined) ? sel.reduce((a, x) => a + x.areaM2, 0) : null;
    return run({ geometry: fc, label: sel.map((x) => x.label).join(", "), extra: { source: "select", areaM2 } });
  }

  // ---- reacting to the store ----
  let source = store.get().tool === "chart" ? store.get().areaFrom : null;
  function sourceChanged() {
    const s = store.get();
    const now = s.tool === "chart" ? s.areaFrom : null;
    if (now === source) return;
    source = now;
    opSeq++;
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

  return { upload, chartSelection, chartView, finishDrawing, restyle, clearShapes, last: () => last, sketch: () => sketch };
}
