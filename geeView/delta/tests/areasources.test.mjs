// Chart area sources: uploaded files become GeoJSON features (port of the
// original's upload, which accepts .zip, .geojson, .json, .kmz and .kml),
// and the map view's label (port of chartMapExtent).
import { test } from "node:test";
import assert from "node:assert/strict";
import { UPLOAD_ACCEPT, uploadKind, convertUrl, featuresFromGeoJSON, featuresFromKml, dropZ, viewLabel, ringBounds } from "../js/engine/areasources.js";

const SQUARE = [[[-111.6, 40.6], [-111.58, 40.6], [-111.58, 40.62], [-111.6, 40.62], [-111.6, 40.6]]];

test("the upload accepts the original's types plus the converter's; only GeoJSON stays in the browser", () => {
  // a shapefile as a .zip, or its parts chosen together
  assert.equal(UPLOAD_ACCEPT, ".zip,.shp,.shx,.dbf,.prj,.cpg,.kml,.kmz,.gpkg,.gpx,.fgb,.geojson,.json");
  assert.equal(uploadKind("a.GeoJSON"), "geojson");
  assert.equal(uploadKind("a.json"), "geojson");
  ["a.kml", "a.zip", "a.kmz", "a.gpkg", "a.gpx", "a.FGB"].forEach((n) => assert.equal(uploadKind(n), "convert", n));
  assert.equal(uploadKind("a.txt"), null);
  assert.equal(uploadKind("a.tif"), null);
});

test("conversion goes to the geeViz server behind the page, never a third party", () => {
  assert.equal(convertUrl("http://127.0.0.1:8889/ee-api", "http://127.0.0.1:8889"), "http://127.0.0.1:8889/ee-api/convert/vector");
  assert.equal(convertUrl("https://askterra.io/ee-api/t/askterra/", "https://askterra.io"), "https://askterra.io/ee-api/t/askterra/convert/vector");
  // direct token mode: no proxy, the local geeView server answers on the page origin
  assert.equal(convertUrl("", "http://localhost:1234"), "http://localhost:1234/ee-api/convert/vector");
});

test("featuresFromGeoJSON: FeatureCollection, Feature or bare geometry; non-polygons left out", () => {
  const fc = { type: "FeatureCollection", features: [{ type: "Feature", properties: { n: 1 }, geometry: { type: "Polygon", coordinates: SQUARE } }, { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [0, 0] } }] };
  assert.equal(featuresFromGeoJSON(fc).length, 1);
  assert.equal(featuresFromGeoJSON(fc[0] || fc.features[0]).length, 1);
  assert.deepEqual(featuresFromGeoJSON({ type: "MultiPolygon", coordinates: [SQUARE] })[0].geometry.type, "MultiPolygon");
  assert.deepEqual(featuresFromGeoJSON({ type: "Polygon", coordinates: SQUARE })[0].geometry.coordinates, SQUARE);
});

test("dropZ: port of fixGeoJSONZ", () => {
  const f = { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [SQUARE[0].map((c) => c.concat([1500]))] } };
  assert.deepEqual(dropZ(f).geometry.coordinates, SQUARE);
});

test("featuresFromKml: every Polygon's outer and inner rings, z dropped", () => {
  const kml = `<?xml version="1.0"?><kml><Document><Placemark><name>A &amp; B</name><MultiGeometry>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      -111.6,40.6,0 -111.58,40.6,0 -111.58,40.62,0 -111.6,40.62,0 -111.6,40.6,0
    </coordinates></LinearRing></outerBoundaryIs>
    <innerBoundaryIs><LinearRing><coordinates>-111.595,40.605 -111.59,40.605 -111.59,40.61 -111.595,40.605</coordinates></LinearRing></innerBoundaryIs></Polygon>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>1,1 2,1 2,2 1,1</coordinates></LinearRing></outerBoundaryIs></Polygon>
  </MultiGeometry></Placemark></Document></kml>`;
  const fs = featuresFromKml(kml);
  assert.equal(fs.length, 2);
  assert.deepEqual(fs[0].geometry.coordinates[0], SQUARE[0]);
  assert.equal(fs[0].geometry.coordinates.length, 2);
  assert.deepEqual(fs[1].geometry.coordinates, [[[1, 1], [2, 1], [2, 2], [1, 1]]]);
});

test("ringBounds and viewLabel", () => {
  assert.deepEqual(ringBounds(featuresFromGeoJSON({ type: "Polygon", coordinates: SQUARE })), { west: -111.6, south: 40.6, east: -111.58, north: 40.62 });
  assert.equal(viewLabel({ west: -111.123456, north: 40.5, east: -110.9, south: 40.25 }), "Map view (-111.123, 40.5, -110.9, 40.25)");
});

// ---- uploads and selections that finish after the user moved on ----
import { createStore } from "../js/state.js";
import { createAreaSources } from "../js/engine/areasources.js";

function fakes() {
  class Data {
    constructor() { this.f = []; }
    setStyle() {}
    forEach(fn) { this.f.slice().forEach(fn); }
    remove(x) { this.f = this.f.filter((y) => y !== x); }
    addGeoJson(gj) { this.f.push(...gj.features); return gj.features; }
  }
  const listeners = {};
  const gmap = {
    addListener: (ev, fn) => (listeners[ev] = fn),
    fitBounds: () => setTimeout(() => listeners.__idleOnce && listeners.__idleOnce(), 0),
    setOptions: () => {},
    getBounds: () => null,
  };
  const google = { Data, event: { addListenerOnce: (m, ev, fn) => (listeners.__idleOnce = fn) } };
  const sent = [];
  const ee = {
    Feature: (g) => (sent.push(g), { dissolve: () => ({ g }) }),
    FeatureCollection: (fs) => ({ fs }),
    Projection: (p) => p,
  };
  return { gmap, google, ee, sent };
}

function deferred() {
  let resolve;
  const p = new Promise((r) => (resolve = r));
  return { p, resolve };
}

const GJ = { type: "FeatureCollection", features: [{ type: "Feature", properties: { secret: "owner name" }, geometry: { type: "Polygon", coordinates: SQUARE } }] };

function setup(areaFrom) {
  const store = createStore();
  const f = fakes();
  const charted = [];
  const charter = { chartArea: (g, label) => (charted.push(label), Promise.resolve()), cancel: () => {} };
  const sel = deferred();
  const sources = createAreaSources({ gmap: f.gmap }, store, charter, {
    google: f.google,
    ee: f.ee,
    query: () => ({ selectionCollection: () => sel.p }),
  });
  store.set({ tool: "chart", areaFrom });
  return { store, sources, charted, sel, sent: f.sent };
}

test("upload: a file converted after the user switched tools charts nothing", async () => {
  const { store, sources, charted } = setup("upload");
  const fetched = deferred();
  const realFetch = globalThis.fetch;
  globalThis.fetch = () => fetched.p;
  try {
    const done = sources.upload({ name: "units.zip" });
    store.set({ tool: "query" });
    fetched.resolve({ ok: true, json: async () => GJ });
    assert.equal(await done, null);
    assert.deepEqual(charted, []);
  } finally {
    globalThis.fetch = realFetch;
  }
});

test("upload: a file read while Upload stays on charts it, sending only geometry", async () => {
  const { sources, charted, sent } = setup("upload");
  await sources.upload({ name: "units.geojson", text: async () => JSON.stringify(GJ) });
  assert.deepEqual(charted, ["units"]);
  assert.deepEqual(sent, [GJ.features[0].geometry], "no properties go to Earth Engine");
});

test("select: selections collected after the source changed chart nothing", async () => {
  const { store, sources, charted, sel } = setup("select");
  store.set({ selections: [{ label: "Selected Units A", areaM2: 1 }] });
  const done = sources.chartSelection();
  store.set({ areaFrom: "view" });
  sel.resolve({ fc: true });
  assert.equal(await done, null);
  assert.deepEqual(charted, []);
});

test("view: the map resting before Earth Engine is ready charts once it is, without touching Earth Engine first", async () => {
  // auto area charting starts on the map's idle event, which can come before
  // Earth Engine has loaded (it loads on demand)
  const store = createStore();
  const f = fakes();
  const made = [];
  f.ee.Geometry = { Rectangle: (c) => (made.push(c), { rect: c }) };
  f.gmap.getBounds = () => ({ toJSON: () => ({ west: -112, south: 40, east: -111, north: 41 }) });
  f.google.LatLng = class {
    constructor(lat, lng) { this.lat = lat; this.lng = lng; }
  };
  const charted = [];
  const charter = { chartArea: (g, label) => (charted.push([g, label]), Promise.resolve()), cancel: () => {} };
  const ee = deferred();
  const sources = createAreaSources({ gmap: f.gmap }, store, charter, { google: f.google, ee: f.ee, ready: () => ee.p, idleDelay: 0 });
  store.set({ tool: "chart", areaFrom: "view" });
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(made, []); // no Earth Engine object before it is ready
  assert.deepEqual(charted, []);
  ee.resolve();
  await new Promise((r) => setTimeout(r, 20));
  assert.equal(charted.length, 1);
  assert.deepEqual(charted[0][0], { rect: [-112, 40, -111, 41] });
  assert.match(charted[0][1], /^Map view/);
  assert.ok(sources);
});
