// The Query tool on ArcGIS map, tile and image services: identify, on
// recorded answers (js/esri/identify.js, js/plugins/esri.js).
import { test } from "node:test";
import assert from "node:assert/strict";
import { fakeFetch, fixture, response } from "./esrifake.mjs";
import { identifyMap, identifyImage, classInfoOf } from "../js/esri/identify.js";
import { queryPoint } from "../js/engine/query.js";

const NFHL = fixture("nfhl_info").request.url;
const TOPO = fixture("topo_info").request.url;
const LCMS = fixture("lcms_info").request.url;
const ZONE = { lng: -105.068, lat: 40.59 };
const VIEW = { bounds: { west: -105.08, south: 40.58, east: -105.056, north: 40.596 }, width: 800, height: 600 };
const LAYER = { id: "layer-1", name: "Flood" };

test("identifyMap asks the visible sublayers within 8 pixels in this view", async () => {
  const fetch = fakeFetch([[NFHL + "/identify", "nfhl_identify"]]);
  const rs = await identifyMap(NFHL, ZONE, VIEW, { layers: "show:28" }, { fetch, info: response("nfhl_info"), layer: LAYER });
  const p = fetch.calls[0].params;
  assert.equal(p.tolerance, "8");
  assert.equal(p.layers, "visible:28");
  assert.equal(p.imageDisplay, "800,600,96");
  assert.equal(p.mapExtent, "-105.08,40.58,-105.056,40.596");
  assert.equal(p.sr, "4326");
  assert.equal(p.returnGeometry, "false");
  assert.deepEqual(JSON.parse(p.geometry), { x: -105.068, y: 40.59, spatialReference: { wkid: 4326 } });
  const hits = response("nfhl_identify").results;
  assert.equal(rs.length, hits.length);
  assert.equal(rs[0].kind, "table");
  assert.equal(rs[0].layerId, "layer-1");
  assert.equal(rs[0].meta, `${hits[0].layerName}: ${hits[0].value}`);
  const keys = rs[0].data.rows.map((r) => r[0]);
  assert.ok(keys.includes("FLD_ZONE"), keys.join(","));
  assert.equal(rs[0].data.rows.find((r) => r[0] === "FLD_ZONE")[1], "AE");
});

test("identifyMap with nothing hit says so", async () => {
  const fetch = fakeFetch([[() => true, { results: [] }]]);
  const rs = await identifyMap(NFHL, ZONE, VIEW, {}, { fetch, info: response("nfhl_info"), layer: LAYER });
  assert.equal(rs.length, 1);
  assert.equal(rs[0].meta, "No features here");
  // no choice: the sublayers drawn by default
  const want = response("nfhl_info").layers.filter((l) => l.defaultVisibility).map((l) => l.id).sort((a, b) => a - b);
  assert.equal(fetch.calls[0].params.layers, "visible:" + want.join(","));
});

test("a tile service answers from the map service behind its tiles", async () => {
  const fetch = fakeFetch([[TOPO + "/identify", "topo_identify"]]);
  const rs = await identifyMap(TOPO, ZONE, VIEW, {}, { fetch, info: response("topo_info"), layer: LAYER });
  assert.equal(rs.length, response("topo_identify").results.length);
});

const LEGEND = {
  type: "images",
  items: response("lcms_legend").layers[0].legend.map((it, i) => ({ label: it.label, src: "data:image/png;base64,", value: i + 1 })),
};

test("classInfoOf reads class values and names from a legend", () => {
  const ci = classInfoOf(LEGEND);
  assert.equal(ci.values.length, 16);
  assert.equal(ci.names[0], "Wind");
  assert.equal(ci.values[0], 1);
  assert.equal(classInfoOf({ type: "images", items: [{ label: "a", src: "" }] }), null);
});

test("identifyImage on a time-enabled class map: the classes over time", async () => {
  const fetch = fakeFetch([[LCMS + "/identify", "lcms_identify"]]);
  const rs = await identifyImage(LCMS, ZONE, {}, LEGEND, { fetch, info: response("lcms_info"), layer: LAYER });
  assert.equal(fetch.calls[0].params.returnCatalogItems, "true");
  assert.equal(fetch.calls[0].params.returnPixelValues, "true");
  assert.equal(rs.length, 1);
  const s = rs[0];
  assert.equal(s.kind, "series");
  const id = response("lcms_identify");
  const years = id.catalogItems.features.map((f) => f.attributes.year).sort((a, b) => a - b);
  assert.deepEqual(s.data.x, years.map(String));
  // values follow their catalog items, then sorted by year
  const byYear = new Map(id.catalogItems.features.map((f, i) => [f.attributes.year, Number(id.properties.Values[i])]));
  assert.deepEqual(s.data.series[0].y, years.map((y) => byYear.get(y)));
  const names = s.data.series[0].labels;
  assert.equal(names[0], LEGEND.items[byYear.get(years[0]) - 1].label);
});

test("identifyImage with no time: one value with its class name; NoData says so", async () => {
  const info = { ...response("lcms_info"), timeInfo: undefined };
  const fetch = fakeFetch([[() => true, { value: "15", properties: null, catalogItems: null }]]);
  const rs = await identifyImage(LCMS, ZONE, {}, LEGEND, { fetch, info, layer: LAYER });
  assert.equal(fetch.calls[0].params.returnCatalogItems, "false");
  assert.equal(rs[0].kind, "value");
  assert.equal(rs[0].data.bands[0].value, 15);
  assert.equal(rs[0].data.bands[0].label, "Stable");
  const none = await identifyImage(LCMS, ZONE, {}, LEGEND, { fetch: fakeFetch([[() => true, { value: "NoData" }]]), info, layer: LAYER });
  assert.equal(none[0].data.bands[0].display, "No data");
});

// queryPoint through the plug-in: errors become one card, stale answers are dropped
function engineFor(layers) {
  return { layers: { queryTarget: async (id) => ({ type: layers.find((l) => l.id === id).kind, item: layers.find((l) => l.id === id).item, viz: {} }) } };
}

test("a service error is one Query failed card, not a rejection", async () => {
  const layers = [{ id: "a", name: "Flood", kind: "esri.map", item: NFHL, visible: true, queryable: true, viz: {} }];
  const fetch = fakeFetch([[NFHL, "nfhl_info"], [NFHL + "/identify", "error_body"]]);
  const got = [];
  const rs = await queryPoint(engineFor(layers), layers, ZONE, {}, { fetch, view: VIEW, onResult: (r) => got.push(r) });
  assert.equal(rs.length, 1);
  assert.equal(rs[0].meta, "Query failed");
  assert.match(rs[0].data.error, /Invalid URL/);
  assert.equal(got.length, 1);
});

test("an identify answer for an old click is dropped", async () => {
  const layers = [{ id: "a", name: "Flood", kind: "esri.map", item: NFHL, visible: true, queryable: true, viz: {} }];
  let current = true;
  const fetch = fakeFetch([[NFHL, "nfhl_info"], [NFHL + "/identify", () => ((current = false), response("nfhl_identify"))]]);
  const got = [];
  const rs = await queryPoint(engineFor(layers), layers, ZONE, {}, { fetch, view: VIEW, token: { isCurrent: () => current }, onResult: (r) => got.push(r) });
  assert.deepEqual(rs, []);
  assert.deepEqual(got, []);
});

test("the values over time are colored by class, even when a swatch has no color", async () => {
  const colors = LEGEND.items.map((it, i) => ({ ...it, color: i === 2 ? null : "#" + String(i).padStart(2, "0") + "aa00" }));
  const fetch = fakeFetch([[LCMS + "/identify", "lcms_identify"]]);
  const [s] = await identifyImage(LCMS, ZONE, {}, { ...LEGEND, items: colors }, { fetch, info: response("lcms_info"), layer: LAYER });
  const cc = s.data.series[0].classColors;
  assert.ok(cc, "class colors on the line");
  const y = s.data.series[0].y;
  y.forEach((v, i) => assert.equal(cc[i], v === 3 ? null : colors[v - 1].color, `value ${v}`));
});
