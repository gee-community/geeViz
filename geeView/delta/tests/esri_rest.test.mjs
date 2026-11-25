// The ArcGIS REST client (js/esri/rest.js), on recorded responses.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture, response } from "./esrifake.mjs";
import {
  EsriError, esriRequest, serviceInfo, serviceKind, isWebMercator, toGeoJSON, toEsriPolygon, timeSteps, catalogYears,
} from "../js/esri/rest.js";

const NFHL = fixture("nfhl_info").request.url;
const TOPO = fixture("topo_info").request.url;
const LCMS = fixture("lcms_info").request.url;
const MTBS63 = fixture("mtbs63_info").request.url;
const STATES = fixture("states_info").request.url;

test("esriRequest asks for JSON and encodes object params as JSON", async () => {
  const fetch = fakeFetch([[() => true, { ok: 1 }]]);
  const out = await esriRequest(STATES + "/query", { where: "1=1", geometry: { x: 1, y: 2 } }, { fetch });
  assert.deepEqual(out, { ok: 1 });
  const req = fetch.calls[0];
  assert.equal(req.method, "GET");
  assert.equal(req.params.f, "json");
  assert.deepEqual(JSON.parse(req.params.geometry), { x: 1, y: 2 });
  // f given is kept
  await esriRequest(STATES + "/query", { f: "geojson" }, { fetch });
  assert.equal(fetch.calls[1].params.f, "geojson");
});

test("esriRequest posts a form when the URL would be too long", async () => {
  const fetch = fakeFetch([[() => true, { ok: 1 }]]);
  const ring = Array.from({ length: 400 }, (_, i) => [-105 + i / 1000, 40 + (i % 7) / 1000]);
  await esriRequest(STATES + "/query", { geometry: { rings: [ring] } }, { fetch, maxGet: 2000 });
  const req = fetch.calls[0];
  assert.equal(req.method, "POST");
  assert.ok(!req.url.includes("geometry="), "the geometry is in the body, not the URL");
  assert.equal(JSON.parse(req.params.geometry).rings[0].length, 400);
  assert.equal(req.params.f, "json");
});

test("an {error} body rejects with the service's message", async () => {
  const fetch = fakeFetch([[() => true, "error_body"]]);
  const body = response("error_body");
  await assert.rejects(esriRequest(STATES + "/999/query", {}, { fetch }), (e) => {
    assert.ok(e instanceof EsriError);
    assert.equal(e.code, 400);
    assert.ok(e.message.includes(body.error.message));
    return true;
  });
});

test("an HTTP error rejects with EsriError", async () => {
  const fetch = fakeFetch([[() => true, { __status: 503 }]]);
  await assert.rejects(esriRequest(STATES, {}, { fetch }), (e) => e instanceof EsriError && e.code === 503);
});

test("a blocked cross-site request says so", async () => {
  const fetch = fakeFetch([[() => true, () => new TypeError("Failed to fetch")]]);
  await assert.rejects(esriRequest(STATES, {}, { fetch }), (e) => {
    assert.ok(e instanceof EsriError);
    assert.equal(e.message, "This service does not allow requests from this page.");
    return true;
  });
});

test("serviceInfo asks once per URL", async () => {
  const fetch = fakeFetch([[NFHL, "nfhl_info"]]);
  const a = await serviceInfo(NFHL, { fetch });
  const b = await serviceInfo(NFHL, { fetch });
  assert.equal(a, b);
  assert.equal(fetch.calls.length, 1);
  assert.equal(a.mapName, response("nfhl_info").mapName);
});

test("serviceKind reads the service type from its URL and metadata", () => {
  assert.equal(serviceKind(NFHL, response("nfhl_info")), "esri.map");
  assert.equal(serviceKind(TOPO, response("topo_info")), "esri.tile");
  assert.equal(serviceKind(LCMS, response("lcms_info")), "esri.image");
  assert.equal(serviceKind(MTBS63, response("mtbs63_info")), "esri.feature");
  assert.equal(serviceKind(STATES, response("states_info")), "esri.feature");
  // a cached image service is tiles, unless a rendering rule or time is asked
  const cachedImage = { tileInfo: { spatialReference: { wkid: 102100 } }, singleFusedMapCache: true };
  assert.equal(serviceKind("https://x/arcgis/rest/services/a/ImageServer", cachedImage), "esri.tile");
  assert.equal(serviceKind("https://x/arcgis/rest/services/a/ImageServer", cachedImage, { time: [0, 1] }), "esri.image");
  // a cached map service in another projection is drawn by export
  const otherSR = { singleFusedMapCache: true, tileInfo: { spatialReference: { wkid: 4326 } } };
  assert.equal(serviceKind("https://x/arcgis/rest/services/a/MapServer", otherSR), "esri.map");
});

test("isWebMercator knows both ids", () => {
  assert.ok(isWebMercator({ wkid: 102100 }));
  assert.ok(isWebMercator({ latestWkid: 3857 }));
  assert.ok(!isWebMercator({ wkid: 4326 }));
  assert.ok(!isWebMercator(null));
});

test("toGeoJSON converts recorded point, polyline and polygon geometries", () => {
  const pt = response("esri_point").features[0].geometry;
  assert.deepEqual(toGeoJSON(pt), { type: "Point", coordinates: [pt.x, pt.y] });
  const line = response("esri_polyline").features[0].geometry;
  const gl = toGeoJSON(line);
  assert.equal(gl.type, line.paths.length > 1 ? "MultiLineString" : "LineString");
  // Hawaii: several islands, each a clockwise outer ring
  const hi = response("esri_polygon").features[0].geometry;
  const gp = toGeoJSON(hi);
  assert.equal(gp.type, "MultiPolygon");
  assert.equal(gp.coordinates.length, hi.rings.length);
  assert.deepEqual(toGeoJSON({ points: [[1, 2], [3, 4]] }), { type: "MultiPoint", coordinates: [[1, 2], [3, 4]] });
  assert.deepEqual(toGeoJSON({ xmin: 0, ymin: 1, xmax: 2, ymax: 3 }).type, "Polygon");
  assert.equal(toGeoJSON(null), null);
});

test("toGeoJSON puts counterclockwise rings in the polygon before them as holes", () => {
  const outer = [[0, 0], [0, 10], [10, 10], [10, 0], [0, 0]]; // clockwise
  const hole = [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]]; // counterclockwise
  const g = toGeoJSON({ rings: [outer, hole] });
  assert.equal(g.type, "Polygon");
  assert.equal(g.coordinates.length, 2);
  const two = toGeoJSON({ rings: [outer, outer.map(([x, y]) => [x + 20, y])] });
  assert.equal(two.type, "MultiPolygon");
});

const signedArea = (ring) => ring.reduce((a, [x, y], i) => {
  const [x2, y2] = ring[(i + 1) % ring.length];
  return a + (x * y2 - x2 * y);
}, 0) / 2;

test("toEsriPolygon makes outer rings clockwise", () => {
  const ccw = [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]];
  const mp = { type: "MultiPolygon", coordinates: [[ccw], [ccw.map(([x, y]) => [x + 20, y])]] };
  const e = toEsriPolygon(mp);
  assert.deepEqual(e.spatialReference, { wkid: 4326 });
  assert.equal(e.rings.length, 2);
  e.rings.forEach((r) => assert.ok(signedArea(r) < 0, "clockwise"));
  const fc = { type: "FeatureCollection", features: [{ type: "Feature", geometry: { type: "Polygon", coordinates: [ccw] } }] };
  assert.equal(toEsriPolygon(fc).rings.length, 1);
});

test("timeSteps: catalog years, an interval, or none", () => {
  const steps = timeSteps(response("lcms_info"), [1985, 1986]);
  assert.deepEqual(steps.map((s) => s.label), ["1985", "1986"]);
  assert.equal(steps[0].time[0], Date.UTC(1985, 0, 1));
  assert.equal(steps[0].time[1], Date.UTC(1986, 0, 1) - 1);
  const yearly = {
    timeInfo: { timeExtent: [Date.UTC(2000, 0, 1), Date.UTC(2002, 11, 31)], defaultTimeInterval: 1, defaultTimeIntervalUnits: "esriTimeUnitsYears" },
  };
  assert.equal(timeSteps(yearly).length, 3);
  assert.deepEqual(timeSteps({}), []);
});

test("catalogYears reads the distinct catalog years", async () => {
  const fetch = fakeFetch([[LCMS + "/query", "lcms_catalog_years"]]);
  const years = await catalogYears(LCMS, response("lcms_info"), { fetch });
  const want = response("lcms_catalog_years").features.map((f) => f.attributes.year);
  assert.deepEqual(years, want.slice().sort((a, b) => a - b));
  assert.equal(fetch.calls[0].params.returnDistinctValues, "true");
  assert.equal(await catalogYears(STATES, {}, { fetch }), null);
});

test("an error with details and no message reads as its details", async () => {
  const fetch = fakeFetch([[() => true, { error: { code: 400, message: "", details: ["'Invalid field: X' parameter is invalid"] } }]]);
  await assert.rejects(esriRequest(STATES + "/query", {}, { fetch }), (e) => e.message === "'Invalid field: X' parameter is invalid");
});
