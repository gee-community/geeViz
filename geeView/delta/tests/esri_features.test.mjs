// Feature layers fetched by the browser for the view, tile by tile, on
// recorded answers (js/esri/features.js), and drawn as canvas tiles.
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture, response } from "./esrifake.mjs";
import { createFeatureSource, scaleAt, oidField } from "../js/esri/features.js";
import { createVectorTileOverlay } from "../js/engine/vectortiles.js";

const STATES = fixture("states_info").request.url;
const MTBS63 = fixture("mtbs63_info").request.url;
const TILE = { x: 3, y: 6 };

const pageRoute = (req) => (req.params.resultOffset === "5" ? response("states_query_z4_page2") : req.params.resultOffset === "10" ? { type: "FeatureCollection", features: [] } : response("states_query_z4"));

test("one query per tile: generalized for the zoom, in WGS84, as GeoJSON when offered", async () => {
  const fetch = fakeFetch([[STATES + "/query", pageRoute]]);
  const src = createFeatureSource(STATES, response("states_info"), {}, { fetch });
  await src.partsFor(TILE, 4);
  const p = fetch.calls[0].params;
  assert.ok(Math.abs(Number(p.maxAllowableOffset) - 360 / (256 * 16)) < 1e-9, p.maxAllowableOffset);
  assert.equal(p.outSR, "4326");
  assert.equal(p.inSR, "3857");
  assert.equal(p.geometryPrecision, "6");
  assert.equal(p.f, "geojson");
  assert.equal(p.spatialRel, "esriSpatialRelIntersects");
  assert.equal(p.geometryType, "esriGeometryEnvelope");
  const env = JSON.parse(p.geometry);
  assert.ok(env.xmin < env.xmax && env.ymin < env.ymax);
  assert.deepEqual(p.outFields.split(",").sort(), ["OBJECTID", "STATE_NAME"]);
  // the same tile again is cached
  await src.partsFor(TILE, 4);
  assert.equal(fetch.calls.filter((c) => c.params.resultOffset === undefined).length, 1);
});

test("pages while the service says there is more", async () => {
  const fetch = fakeFetch([[STATES + "/query", pageRoute]]);
  const status = [];
  const src = createFeatureSource(STATES, response("states_info"), {}, { fetch, onStatus: (s) => status.push(s) });
  const parts = await src.partsFor(TILE, 4);
  assert.deepEqual(fetch.calls.map((c) => c.params.resultOffset), [undefined, "5", "10"]);
  const n = response("states_query_z4").features.length + response("states_query_z4_page2").features.length;
  assert.equal(new Set(parts.map((p) => p.fid)).size, n);
  assert.equal(status[status.length - 1].capped, false);
});

test("maxFeatures caps a tile and says so", async () => {
  const fetch = fakeFetch([[STATES + "/query", pageRoute]]);
  const status = [];
  const src = createFeatureSource(STATES, response("states_info"), { maxFeatures: 3 }, { fetch, onStatus: (s) => status.push(s) });
  const parts = await src.partsFor(TILE, 4);
  assert.equal(fetch.calls.length, 1);
  assert.equal(fetch.calls[0].params.resultRecordCount, "3");
  assert.equal(new Set(parts.map((p) => p.fid)).size, 3);
  assert.deepEqual({ capped: status[0].capped, shown: status[0].shown }, { capped: true, shown: 3 });
});

test("maxLayerMB stops new tiles once the layer has fetched that much", async () => {
  const fetch = fakeFetch([[STATES + "/query", pageRoute]]);
  const status = [];
  const src = createFeatureSource(STATES, response("states_info"), { maxLayerMB: 0.001 }, { fetch, onStatus: (s) => status.push(s) });
  await src.partsFor(TILE, 4);
  const before = fetch.calls.length;
  const parts = await src.partsFor({ x: 2, y: 6 }, 4);
  assert.equal(fetch.calls.length, before, "no request past the budget");
  assert.deepEqual(parts, []);
  assert.equal(status[status.length - 1].capped, true);
});

test("outside the layer's scale range nothing is fetched", async () => {
  const fetch = fakeFetch([[STATES + "/query", pageRoute]]);
  const status = [];
  const info = response("states_info"); // minScale 150,000,000
  assert.ok(scaleAt(1) > info.minScale && scaleAt(2) < info.minScale);
  const src = createFeatureSource(STATES, info, {}, { fetch, onStatus: (s) => status.push(s) });
  assert.deepEqual(await src.partsFor({ x: 0, y: 0 }, 1), []);
  assert.equal(fetch.calls.length, 0);
  assert.equal(status[0].outOfScale, true);
});

test("Esri JSON answers become parts keyed by the object id; where and time are sent", async () => {
  const info = { ...response("mtbs63_info"), supportedQueryFormats: "JSON" };
  assert.equal(oidField(info), "objectid");
  const fetch = fakeFetch([[MTBS63 + "/query", "mtbs63_query"]]);
  const src = createFeatureSource(MTBS63, info, { where: "year = 2020", time: [1, 2], simplify: false }, { fetch });
  const parts = await src.partsFor({ x: 852, y: 1550 }, 12);
  const p = fetch.calls[0].params;
  assert.equal(p.f, "json");
  assert.equal(p.where, "year = 2020");
  assert.equal(p.time, "1,2");
  assert.equal(p.maxAllowableOffset, undefined, "simplify: false asks for exact geometry");
  const oid = response("mtbs63_query").features[0].attributes.objectid;
  assert.ok(parts.length > 0 && parts.every((x) => x.fid === oid));
  assert.equal(parts[0].props.fire_name, "CAMERON PEAK");
});

// ---- the overlay, fed by a source ----
function fakeDoc() {
  const canvases = [];
  return {
    canvases,
    createElement() {
      const c = { style: {}, draws: 0, width: 0, height: 0 };
      const ctx2d = new Proxy({}, { get: (t, k) => (k === "fill" || k === "stroke" ? () => c.draws++ : t[k] !== undefined ? t[k] : () => {}), set: (t, k, v) => ((t[k] = v), true) });
      c.getContext = () => ctx2d;
      canvases.push(c);
      return c;
    },
  };
}
const fakeGoogle = { Size: function () {} };

test("a canvas released before its features arrive is not drawn on", async () => {
  let resolve;
  const source = { partsFor: () => new Promise((r) => (resolve = r)) };
  const ov = createVectorTileOverlay({ google: fakeGoogle, source, style: { strokeColor: "#f00" } });
  const doc = fakeDoc();
  const canvas = ov.getTile({ x: 3, y: 6 }, 4, doc);
  ov.releaseTile(canvas);
  await new Promise((r) => setTimeout(r, 0)); // the overlay asks for parts in a microtask
  resolve(response("states_query_z4").features.map((f) => ({ kind: "polygon", coords: f.geometry.coordinates, bbox: [-180, -90, 180, 90], fid: f.id, props: f.properties })));
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(canvas.draws, 0);
  assert.deepEqual(ov.stats(), { total: 0, loaded: 0, failed: 0 });
});

test("a source tile counts as loading until its features arrive, then draws", async () => {
  const fetch = fakeFetch([[STATES + "/query", pageRoute]]);
  const source = createFeatureSource(STATES, response("states_info"), {}, { fetch });
  const ov = createVectorTileOverlay({ google: fakeGoogle, source, style: { strokeColor: "#f00", fillColor: "#f00", fillOpacity: 0.2 } });
  const doc = fakeDoc();
  const canvas = ov.getTile(TILE, 4, doc);
  assert.deepEqual(ov.stats(), { total: 1, loaded: 0, failed: 0 });
  await new Promise((r) => setTimeout(r, 20));
  assert.deepEqual(ov.stats(), { total: 1, loaded: 1, failed: 0 });
  assert.ok(canvas.draws > 0);
  assert.ok(ov.loadedParts().length > 0);
});
